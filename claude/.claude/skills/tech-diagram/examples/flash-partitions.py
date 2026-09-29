"""Flash 分区：STM32F407 内部 1 MiB Flash 上的 MCUboot A/B 布局。分区必须对齐到（大小不一的）擦除扇区。"""

KiB = 1024
F = 0x08000000
hx = lambda a: f"0x{a:08x}"

# RM0090: sectors 0-3 = 16 KiB, 4 = 64 KiB, 5-11 = 128 KiB
SECTORS = [16] * 4 + [64] + [128] * 7
SLOT0, SLOT1, SLOT_SZ = F + 0x20000, F + 0x80000, 0x60000
IMG = SLOT0 + 0x200                      # MCUboot image header is 0x200 bytes; the vector table follows it
IMG_END = SLOT0 + 0x2E600                # illustrative app size
TLV_END = IMG_END + 0x100
TRAILER = SLOT0 + SLOT_SZ - 0x400


def build(d):
    d.title("Flash 分区：MCUboot 双槽升级", eyebrow="嵌入式 · STM32F407 内部 Flash 1 MiB",
            subtitle="每个分区的边界都落在擦除扇区边界上；新固件先写进 slot1，重启后 MCUboot 校验签名、"
                     "借 scratch 扇区把两个槽逐扇区交换，再跳到 slot0 里的应用。")
    m = d.memmap([
        dict(name="scratch", start=F + 0xE0000, size=128 * KiB, sub=["交换时暂存一个扇区"], tone="slate"),
        dict(name="slot1 · secondary", start=SLOT1, size=SLOT_SZ, tone="violet", sub=["待升级镜像 v1.3（下载写入这里）"]),
        dict(name="slot0 · primary", start=SLOT0, size=SLOT_SZ, tone="blue", state="accent", gap_label="空闲",
             children=[
                 dict(name="trailer", start=TRAILER, end=SLOT0 + SLOT_SZ, sub=["swap 状态 · image_ok · magic"]),
                 dict(name="TLV", start=IMG_END, end=TLV_END, sub=["SHA-256 · ECDSA 签名"]),
                 dict(name="应用镜像 v1.2", start=IMG, end=IMG_END, tone="blue", sub=["向量表 · .text · .rodata"]),
                 dict(name="image header", start=SLOT0, end=IMG, sub=["magic · 版本 · 镜像大小"]),
             ]),
        dict(name="littlefs", start=F + 0x10000, size=64 * KiB, sub=["日志 / 文件"]),
        dict(name="storage", start=F + 0x8000, size=32 * KiB, sub=["NVS 设置"]),
        dict(name="MCUboot", start=F, size=32 * KiB, tone="amber", sub=["复位后最先运行"]),
    ], title="内部 Flash", addr_fmt=hx, min_h=28, max_h=60, w=300, id="flash")
    m.at(0, 0)
    m.pointer(IMG, "VTOR")
    # erase sectors: one bar per sector, in a lane beside the partitions
    a = F
    for i, kb in enumerate(SECTORS):
        m.overlay(a, a + kb * KiB, f"S{i} · {kb}K", tone="slate", id=f"S{i}")
        a += kb * KiB
    m.overlay(F, F + 32 * KiB, "写保护 WRP", tone="rose")
    m.span(SLOT0, F + 0x100000, "MCUboot\n管理的镜像区")
    d.note("S4 只有 64 KiB，放不下一个 128 KiB 的槽扇区——所以槽从 S5 开始，S4 留给文件系统。", w=240) \
        .below(m, gap=32, align="right")
    d.legend(("state", "accent", "正在运行的镜像"))
    d.footer("扇区大小按 RM0090；分区按 MCUboot swap-using-scratch 的常见做法，应用大小与 trailer 长度为示意值。")
