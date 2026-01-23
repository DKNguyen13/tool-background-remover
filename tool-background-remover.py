import os
from rembg import remove
from PIL import Image

# Folder containing original images
input_folder = "input_images"
# Folder to save images after background removal
output_folder = "output_images"

# Create input folder if it doesn't exist
if not os.path.exists(input_folder):
    os.makedirs(input_folder)
    print(f"Input folder '{input_folder}' not found. Folder created. Please add images and run the script again.")
    exit()

# Create output folder if it doesn't exist
os.makedirs(output_folder, exist_ok=True)

# Get list of all images in input folder
images = [f for f in os.listdir(input_folder) if f.lower().endswith((".png", ".jpg", ".jpeg"))]

if not images:
    print(f"Input folder '{input_folder}' is empty. Please add images and run the script again.")
    exit()

# Process each image
for filename in images:
    input_path = os.path.join(input_folder, filename)
    output_path = os.path.join(output_folder, filename)

    with Image.open(input_path) as img:
        img_no_bg = remove(img)  # Remove background
        img_no_bg.save(output_path)

    print(f"Processed: {filename}")

print(f"Done! {len(images)} images have been background removed and saved to '{output_folder}'.")