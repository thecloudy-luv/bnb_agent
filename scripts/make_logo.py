"""Script to generate the 256x256 TiltBalance logo."""

from pathlib import Path
from PIL import Image, ImageDraw


def generate_logo(output_path: Path) -> None:
    """Generate a 256x256 PNG logo representing TiltBalance."""
    size = (256, 256)
    img = Image.new("RGBA", size, (18, 20, 29, 255))
    draw = ImageDraw.Draw(img)

    # Outer border circle in BNB gold
    gold = (240, 185, 11, 255)
    soft_gold = (240, 185, 11, 100)
    cyan = (0, 210, 180, 255)
    white = (255, 255, 255, 255)

    # Decorative background circles
    draw.ellipse((8, 8, 248, 248), outline=soft_gold, width=2)
    draw.ellipse((14, 14, 242, 242), outline=gold, width=4)

    # Fulcrum base (triangle at bottom center: x=128, y=170)
    draw.polygon([(128, 145), (105, 195), (151, 195)], fill=gold)
    draw.rectangle([(95, 195), (161, 205)], fill=gold)

    # Fulcrum pivot circle
    draw.ellipse((122, 139, 134, 151), fill=white)

    # Tilted balance beam (tilted slightly, e.g. from (48, 120) to (208, 140))
    draw.line([(50, 122), (206, 142)], fill=white, width=6)

    # Left pan (higher, e.g. WBNB side)
    draw.line([(55, 123), (40, 155)], fill=soft_gold, width=2)
    draw.line([(55, 123), (70, 155)], fill=soft_gold, width=2)
    draw.chord([(35, 150), (75, 170)], start=0, end=180, fill=gold)

    # Right pan (lower, e.g. BUSD side)
    draw.line([(201, 142), (186, 174)], fill=soft_gold, width=2)
    draw.line([(201, 142), (216, 174)], fill=soft_gold, width=2)
    draw.chord([(181, 169), (221, 189)], start=0, end=180, fill=cyan)

    # Small decorative diamond at top
    draw.polygon([(128, 45), (138, 60), (128, 75), (118, 60)], fill=gold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    print(f"Saved logo to {output_path}")


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "src" / "agent" / "static" / "logo.png"
    generate_logo(target)
