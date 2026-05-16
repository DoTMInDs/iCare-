# generate_icons.py
from PIL import Image
import os

# Open the original WebP image
img = Image.open('RoboForex-Logo.webp')

# Convert to RGBA if needed
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Create icons directory if it doesn't exist
icons_dir = 'static/imgs/icons'
os.makedirs(icons_dir, exist_ok=True)

# Define required sizes
icon_sizes = [16, 32, 64, 72, 96, 128, 144, 152, 167, 180, 192, 384, 512]

# Generate PNG icons for PWA
for size in icon_sizes:
    # Resize image
    img_resized = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Save as PNG (required for PWA icons)
    output_path = os.path.join(icons_dir, f'icon-{size}x{size}.png')
    img_resized.save(output_path, 'PNG', optimize=True)
    print(f'Generated: {output_path}')

# Generate favicon.ico (multiple sizes in one file)
favicon_sizes = [16, 32, 48]
favicon_images = []

for size in favicon_sizes:
    img_resized = img.resize((size, size), Image.Resampling.LANCZOS)
    favicon_images.append(img_resized)

# Save as ICO file
favicon_path = 'static/favicon.ico'
favicon_images[0].save(
    favicon_path, 
    format='ICO', 
    sizes=[(s, s) for s in favicon_sizes],
    append_images=favicon_images[1:]
)
print(f'Generated: {favicon_path}')

# Also save original WebP as fallback
img.save('static/imgs/icons/logo.webp', 'WEBP', quality=85)
print('Generated: static/imgs/icons/logo.webp')

print('\n✅ All icons generated successfully!')