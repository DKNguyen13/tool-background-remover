# ImgTool — BG Remover · Game Dev Edition

Công cụ xoá nền ảnh chuyên dụng cho game dev với:
- **Alpha Matting** → cắt cạnh sắc nét, không còn viền trắng/đen
- **Edge Refinement** → feather, contract, expand mask tùy chỉnh
- **Colour Decontamination** → xoá màu nền bám vào viền sprite
- **Pre/Post Processing** → upscale nhỏ trước khi AI xử lý, trim, padding, power-of-two
- **GUI dark theme** + batch processing + before/after preview
- **Spritesheet packer** (code có sẵn trong `postprocess/refiner.py`)

## Cài đặt

```bash
pip install -r requirements.txt
```

> **GPU (nhanh hơn 5–10×):** cài `onnxruntime-gpu` thay `onnxruntime`

## Chạy GUI

```bash
python main.py
```

## Cấu trúc thư mục

```
imgtool/
├── main.py                  ← GUI chính
├── requirements.txt
├── remove_bg/
│   └── remover.py           ← Core AI + alpha matting + edge refine
├── preprocess/
│   └── processor.py         ← Upscale, sharpen trước khi xoá nền
├── postprocess/
│   └── refiner.py           ← Trim, padding, power-of-two, spritesheet packer
├── optimize/
│   └── optimizer.py         ← Lưu PNG/WebP tối ưu
└── dataset/
    └── manager.py           ← Quản lý batch job, thống kê
```

## Các model AI

| Model | Tốc độ | Độ chính xác | Phù hợp |
|---|---|---|---|
| `u2net` | Trung bình | Cao | Mọi loại ảnh |
| `u2netp` | Nhanh | Vừa | Prototype nhanh |
| `u2net_human_seg` | Trung bình | Cao (người) | Nhân vật game |
| `isnet-general-use` | Chậm | Rất cao | Sprite phức tạp |
| `silueta` | Nhanh | Cao | Vật thể rõ ràng |

## Tips cho game dev

- **Alpha Matting ON** luôn → cạnh sắc nét hơn rembg thường
- **FG threshold 240 / BG threshold 10** → mặc định tốt cho sprite nền sáng
- **Contract 1-2px** → bỏ viền nền bám vào sprite
- **Power-of-two** → bật nếu engine yêu cầu texture 2^n (Unity, Godot cũ)
- **Padding 2px** → tránh sprite bị clip khi tiled
- **Model `isnet-general-use`** → tốt nhất cho tóc, lông, chi tiết mỏng

## Batch processing (CLI)

```python
from pathlib import Path
from remove_bg.remover import remove_background, RemoverConfig, collect_images
from preprocess.processor import preprocess, PreprocessConfig
from postprocess.refiner import postprocess, PostprocessConfig
from optimize.optimizer import save_optimized, OptimizeConfig
from PIL import Image

cfg_rem  = RemoverConfig(alpha_matting=True)
cfg_pre  = PreprocessConfig()
cfg_post = PostprocessConfig(auto_trim=True, padding=2)
cfg_opt  = OptimizeConfig(format="PNG")

for path in collect_images(Path("input_images")):
    img = Image.open(path).convert("RGBA")
    proc, orig_size, was_up = preprocess(img, cfg_pre)
    result = remove_background(proc, cfg_rem)
    result = postprocess(result, orig_size if was_up else None, cfg_post)
    save_optimized(result, Path("output_nobg") / path.stem, cfg_opt)
    print(f"{path.name}")
```
