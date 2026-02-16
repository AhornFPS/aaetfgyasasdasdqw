from PIL import Image
import os

def convert_png_to_ico(png_path, ico_path):
    if not os.path.exists(png_path):
        print(f"Error: {png_path} not found.")
        return False
    
    img = Image.open(png_path)
    # Standard sizes for Windows ICO
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, sizes=icon_sizes)
    print(f"Successfully converted {png_path} to {ico_path}")
    return True

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(base_dir, "assets", "Images", "BetterPlannetsideIcon.png")
    ico_path = os.path.join(base_dir, "assets", "Images", "BetterPlannetsideIcon.ico")
    convert_png_to_ico(png_path, ico_path)
