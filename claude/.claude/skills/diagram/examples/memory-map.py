"""嵌入式启动：STM32F407（Cortex-M4）上电后，向量表 → Reset_Handler → .data 从 Flash 复制到 SRAM、.bss 清零。"""

KiB, MiB = 1024, 1024 * 1024
hx = lambda a: f"0x{a:08x}"

# illustrative firmware laid out by ST's STM32F407VGTx_FLASH.ld (section sizes are made up, symbols are real)
FLASH, SRAM = 0x08000000, 0x20000000
ISR_END, TEXT_END, RODATA_END = 0x08000188, 0x08003A5C, 0x08003D90
SIDATA, DATA_SZ, BSS_END = RODATA_END, 0x68, 0x20000520
HEAP_END, ESTACK, STACK_SZ = 0x20000720, 0x20020000, 0x400
RESET = 0x08000F24


def build(d):
    d.title("MCU 启动：向量表、LMA 与 VMA", eyebrow="嵌入式 · STM32F407 · Cortex-M4",
            subtitle="复位后内核从 0x0 取两个字：初始 MSP 和 Reset_Handler 地址；Reset_Handler 再把 .data 从 Flash（LMA）"
                     "搬到 SRAM（VMA）并清零 .bss，然后才进 main。")
    ov = d.memmap([
        dict(name="Cortex-M4 内核外设", start=0xE0000000, size=1 * MiB, kind="reserved", sub=["NVIC · SysTick · SCB"]),
        dict(name="FSMC", start=0x60000000, end=0xA0000000, kind="reserved", sub=["外部 SRAM / NOR / NAND"]),
        dict(name="片上外设", start=0x40000000, end=0x50060C00, kind="reserved", sub=["APB1/2 · AHB1/2"]),
        dict(name="SRAM1 + SRAM2", start=SRAM, size=128 * KiB, tone="green", perm="rwx"),
        dict(name="系统存储器", start=0x1FFF0000, size=30 * KiB, sub=["ST 出厂 bootloader"]),
        dict(name="CCM RAM", start=0x10000000, size=64 * KiB, sub=["仅 CPU 数据总线"]),
        dict(name="Flash", start=FLASH, size=1 * MiB, tone="blue", perm="r-x"),
        dict(name="启动别名", start=0, size=1 * MiB, kind="ghost", sub=["BOOT0=0 → 映射 Flash"]),
    ], title="4 GiB 地址空间", addr_fmt=hx, bounds=(0, 1 << 32), gap_label="", max_h=64, w=236, id="ov")
    ov.at(0, 0)
    sram = d.memmap([
        dict(name="stack", start=ESTACK - STACK_SZ, end=ESTACK, grow="down", tone="amber",
             sub=["_Min_Stack_Size = 1 KiB"]),
        dict(name="heap", start=BSS_END, end=HEAP_END, grow="up", sub=["_sbrk 从 _end 往上"]),
        dict(name=".bss", start=SRAM + DATA_SZ, end=BSS_END, tone="green", sub=["Reset_Handler 清零"]),
        dict(name=".data（VMA）", start=SRAM, size=DATA_SZ, tone="green", state="accent",
             sub=["运行地址：代码按这里访问"]),
    ], title="SRAM（放大）", addr_fmt=hx, gap_label="空闲", max_h=56, bounds=(SRAM, ESTACK), w=236, id="sram")
    flash = d.memmap([
        dict(name=".data 初值（LMA）", start=SIDATA, size=DATA_SZ, tone="blue", state="accent",
             sub=["加载地址：烧录时放这里"]),
        dict(name=".rodata", start=TEXT_END, end=RODATA_END),
        dict(name=".text", start=ISR_END, end=TEXT_END, tone="blue", sub=["Reset_Handler · main …"]),
        dict(name=".isr_vector", start=FLASH, end=ISR_END, tone="blue", sub=["98 个向量 × 4 B"]),
    ], title="Flash（放大）", addr_fmt=hx, gap_label="空闲", max_h=56, bounds=(FLASH, FLASH + 1 * MiB),
        w=236, id="flash")
    flash.right_of(ov, gap=150, align="bottom")
    sram.right_of(flash, gap=190, align="top")
    sram.y = ov.y - 10
    sram.pointer(BSS_END, "_ebss, _end")
    sram.pointer(SRAM + DATA_SZ, "_edata, _sbss")
    sram.pointer(SRAM, "_sdata")
    flash.pointer(SIDATA, "_sidata")
    d.zoom(ov["SRAM1 + SRAM2"], sram)
    d.zoom(ov["Flash"], flash)
    # vector table: the first words the core fetches after reset
    vt = d.array([hx(ESTACK), hx(RESET | 1), "0x08000f79", "…"], orient="v", id="vt", title="向量表 @0x0（= Flash 起始）",
                 index=["MSP +0x00", "Reset +0x04", "NMI +0x08", ""],
                 states={0: "focus", 1: "focus"})
    vt.below(sram, gap=120, align="right")
    top = sram.rect
    X = sram.ext.x1 + 20
    d.edge(vt[0], (top.x1 - 40, top.y0), "① MSP = _estack", state="focus", src_side="right", dst_side="top",
           via=[(X, vt[0].rect.cy), (X, top.y0 - 36), (top.x1 - 40, top.y0 - 36)])
    d.edge(vt[1], flash.addr(RESET), "② PC = Reset_Handler", state="focus")
    d.band(flash[".data 初值（LMA）"], sram[".data（VMA）"], "③ 复制 .data", tone="green", arrow=True)
    d.footer("各段大小为示意值（符号名来自 ST 的链接脚本）；芯片地址来自 RM0090 存储器映射。高度按大小取对数。")
