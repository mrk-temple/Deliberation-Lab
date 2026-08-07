"""下载 + 处理素材：人物头像（灰度圆裁）、瓷器文物（装饰）、欢迎页雕塑水印。
只从 Wikimedia Commons 取图（自动免费授权）。失败的人物前端回退到印章。
重复运行安全：已存在的成品会跳过下载。运行：python fetch_assets.py
"""
import io
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

IMG = Path(__file__).parent / "static" / "img"
AV = IMG / "av"
DECO = IMG / "deco"
for d in (AV, DECO):
    d.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "JiehuoCouncil/1.0 (personal project)"}


def fetch(filename: str, width: int = 900) -> bytes | None:
    enc = urllib.parse.quote(filename)
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{enc}?width={width}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
        return data if len(data) > 20000 else None
    except Exception:
        return None


def fetch_first(cands: list[str], width: int = 900) -> bytes | None:
    for f in cands:
        data = fetch(f, width)
        if data:
            print(f"    ✓ {f}")
            return data
    return None


def square_grayscale(data_or_img, side: int = 320, top_bias: float = 0.04) -> Image.Image:
    img = data_or_img if isinstance(data_or_img, Image.Image) else Image.open(io.BytesIO(data_or_img))
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = int(h * top_bias)
    top = max(0, min(top, h - s))
    img = img.crop((left, top, left + s, top + s))
    img = ImageOps.grayscale(img)                       # 统一灰度——百家同堂不突兀
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Brightness(img).enhance(1.04)
    return img.convert("RGB").resize((side, side), Image.LANCZOS)


# ── 头像：id -> Commons 候选文件名 ──
AVATARS = {
    "laozi": ["Zhang Lu-Laozi Riding an Ox (cropped).jpg", "Zhang Lu-Laozi Riding an Ox.jpg", "Laozi.jpg", "Laozi 002.jpg"],
    "wangyangming": ["Wang-yang-ming.jpg", "Wang Yangming.jpg"],
    "nietzsche": ["Nietzsche187a.jpg", "Friedrich Nietzsche 1882.jpg", "Friedrich Nietzsche-1872.jpg"],
    "camus": ["Albert Camus, gagnant de prix Nobel, portrait en buste, posé au bureau, faisant face à gauche, cigarette de tabagisme.jpg"],
    "jung": ["Carl Gustav Jung (1935).jpg", "CGJung.jpg", "Carl Jung 1910.png"],
    "naval": ["Naval Ravikant.jpg", "Naval Ravikant (cropped).jpg"],
    "maozedong": ["1930s Mao Zedong (cropped1to1).jpg", "1930s Mao Zedong (cropped).jpg", "1930s Mao Zedong.jpg"],
    "kongzi": ["Cropped version of Confucius Portrait, Kongzi (Confucius) Family Mansion, Qufu (13044335945).jpg",
               "Confucius Portrait, Kongzi (Confucius) Family Mansion, Qufu (13044352105).jpg"],
    "zhuangzi": ["Zhuangzi.png"],
    "sushi": ["Su shi wearing Dongpo jin.jpg", "Su Dongpo portrait at Garden of Pleasance-20241023.jpg"],
    "feynman": ["Richard Feynman 1959.png", "Feynman-richard p.jpg",
                "RichardFeynman-PaineMansionWoods1984 copyrightTamikoThiel bw.jpg"],
    "tarot": ["RWS Tarot 00 Fool.jpg"],
}
# 本地已有的雕塑头像
LOCAL_AVATARS = {"socrates": IMG / "socrates.jpg", "marcus-aurelius": IMG / "marcus.jpg"}

print("头像：")
for pid, src in LOCAL_AVATARS.items():
    if src.exists():
        square_grayscale(Image.open(src)).save(AV / f"{pid}.jpg", quality=88)
        print(f"  {pid}: 本地雕塑 ✓")
for pid, cands in AVATARS.items():
    out = AV / f"{pid}.jpg"
    if out.exists():
        print(f"  {pid}: 已存在，跳过")
        continue
    print(f"  {pid}:")
    data = fetch_first(cands)
    if data:
        try:
            square_grayscale(data).save(out, quality=88)
            print(f"    → 已保存 {out.name}")
        except Exception as e:
            print(f"    ✗ 处理失败 {e}")
    else:
        print("    ✗ 无免费图，回退印章")

# ── 文物（瓷器，青瓷与主题相配）：装饰用 ──
ARTIFACTS = [
    ("celadon", ["Southern Song Longquan Ware Celadon Vase 1.jpg",
                 "Southern Song Longquan Ware Celadon Cong-shaped Vase.jpg",
                 "Northern Song Longquan Ware Vase.jpg", "Song Dynasty Celadon Vase.jpg"]),
    ("porcelain", ["Lidded Prunus Vase (Meiping) with Lotus Sprays LACMA AC1999.38.6.1-.2.jpg",
                   "Porcelain Vase.jpg"]),
]
print("文物：")
for name, cands in ARTIFACTS:
    out = DECO / f"{name}.png"
    if out.exists():
        print(f"  {name}: 已存在，跳过")
        continue
    data = fetch_first(cands, width=700)
    if data:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((520, 760), Image.LANCZOS)
        img.save(out)
        print(f"  {name}: → {out.name}")
    else:
        print(f"  {name}: ✗ 未找到")

# ── 欢迎页雕塑水印（用柏拉图全身胸像，灰度纵向裁切）──
hero = IMG / "hero.jpg"
if not hero.exists() and (IMG / "plato.jpg").exists():
    img = ImageOps.exif_transpose(Image.open(IMG / "plato.jpg")).convert("RGB")
    img = ImageOps.grayscale(img).convert("RGB")
    img.thumbnail((640, 900), Image.LANCZOS)
    img.save(hero, quality=86)
    print("水印：hero.jpg ✓")

print("完成。")
