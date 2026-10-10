"""x86-64 内核虚拟地址布局（4 级页表），与物理内存的两条映射。布局取自 Documentation/arch/x86/x86_64/mm.rst（v6.6）。"""

KiB, MiB, GiB, TiB = 1 << 10, 1 << 20, 1 << 30, 1 << 40
PAGE_OFFSET = 0xffff888000000000
KTEXT = 0xffffffff80000000


def build(d):
    d.title("x86-64 内核地址空间：同一块物理内存，两个虚拟地址", eyebrow="Linux 内核 · 4 级页表 · 48 位",
            subtitle="直接映射区把全部物理内存按 VA = PA + page_offset_base 线性映射；内核映像又在 __START_KERNEL_map "
                     "处被映射一次。vmalloc、vmemmap、模块等各占一段，中间是大量未用空洞。")
    va = d.memmap([
        dict(name="用户空间", start=0, last=0x00007fffffffffff, kind="reserved", sub=["每个进程一份"]),
        dict(name="非规范地址空洞", start=0x0000800000000000, last=0xffff7fffffffffff, kind="free"),
        dict(name="guard hole", start=0xffff800000000000, last=0xffff87ffffffffff, kind="reserved",
             sub=["hypervisor 保留"]),
        dict(name="LDT remap（PTI）", start=0xffff880000000000, last=0xffff887fffffffff),
        dict(name="直接映射区", start=PAGE_OFFSET, last=0xffffc87fffffffff, tone="teal", state="accent",
             sub=["全部物理内存 · kmalloc 返回这里"]),
        dict(name="vmalloc / ioremap", start=0xffffc90000000000, last=0xffffe8ffffffffff, tone="violet",
             sub=["虚拟连续、物理零散"]),
        dict(name="vmemmap", start=0xffffea0000000000, last=0xffffeaffffffffff, tone="violet",
             sub=["struct page 数组"]),
        dict(name="KASAN shadow", start=0xffffec0000000000, last=0xfffffbffffffffff, kind="reserved",
             sub=["仅 CONFIG_KASAN"]),
        dict(name="cpu_entry_area", start=0xfffffe0000000000, last=0xfffffe7fffffffff),
        dict(name="%esp fixup stacks", start=0xffffff0000000000, last=0xffffff7fffffffff),
        dict(name="EFI 运行时映射", start=0xffffffef00000000, last=0xfffffffeffffffff),
        dict(name="内核映像映射", start=KTEXT, last=0xffffffff9fffffff, tone="amber", state="accent",
             sub=["映射到物理 0 起的 512 MiB"]),
        dict(name="模块", start=0xffffffffa0000000, last=0xfffffffffeffffff, tone="amber", sub=["insmod 的代码"]),
        dict(name="fixmap", start=0xffffffffff580000, last=0xffffffffff5fffff, sub=["起点可变"]),
        dict(name="vsyscall", start=0xffffffffff600000, last=0xffffffffff600fff),
    ], title="虚拟地址空间（内核视角）", addr_fmt="{:016x}", bounds=(0, 1 << 64), gap_label="未用",
        min_h=24, max_h=64, id="va")
    va.at(0, 0)
    va.span("用户空间", label="用户\n128 TiB", side="left")
    va.span("guard hole", "vsyscall", "内核\n128 TiB", side="left")
    va.pointer("直接映射区", "page_offset_base", at="start")
    va.pointer("vmalloc / ioremap", "vmalloc_base", at="start")
    va.pointer("vmemmap", "vmemmap_base", at="start")
    va.pointer("内核映像映射", "__START_KERNEL_map", at="start")

    # an example 16 GiB machine (e820): RAM below 3 GiB, the PCI hole, the rest remapped above 4 GiB
    pa = d.memmap([
        dict(name="低 1 MiB", start=0, size=1 * MiB, kind="reserved", sub=["BIOS · 实模式"]),
        dict(name="RAM · ZONE_DMA", start=1 * MiB, end=16 * MiB),
        dict(name="内核映像", start=16 * MiB, size=44 * MiB, tone="amber", sub=["_text … _end · 默认 16 MiB 起"]),
        dict(name="RAM · ZONE_DMA32", start=60 * MiB, end=3 * GiB),
        dict(name="PCI MMIO 空洞", start=3 * GiB, end=4 * GiB, kind="reserved", sub=["设备寄存器，不是内存"]),
        dict(name="RAM · ZONE_NORMAL", start=4 * GiB, end=17 * GiB, sub=["3 GiB 以上的 13 GiB"]),
    ], title="物理地址空间（16 GiB 内存示例）", addr_fmt=lambda a: f"0x{a:x}", addr_side="right", max_h=90,
        id="pa")
    pa.right_of(va, gap=230, align="bottom").shift(0, -150)
    d.band(va["直接映射区"], pa, "VA = PA + page_offset_base", tone="teal", label_at=0.42)
    d.band(va["内核映像映射"], pa.range(0, 512 * MiB), "VA = PA + __START_KERNEL_map", tone="amber", label_at=0.6)
    d.note("同一个物理页可以有两个内核虚拟地址：__pa() / __va() 只对直接映射区做加减；"
           "内核代码自己的地址要用 __pa_symbol()。", w=300).below(pa, gap=40, align="left")
    d.footer("开启 KASLR（CONFIG_RANDOMIZE_MEMORY）时 page_offset_base / vmalloc_base / vmemmap_base 会被随机化；"
             "表中是未随机化的默认值。高度按大小取对数。")
