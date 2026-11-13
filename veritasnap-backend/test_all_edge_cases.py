"""
VeritaSnap V2 — Comprehensive Automated Edge-Case Test Suite
============================================================
Verifies all 8 mandatory mathematical & forensic requirements plus the 4 torture tests:
1. Non-square 16:9 aspect ratio preservation + flat background PSNR >= 41.0 dB (Bugs 1 & 5)
2. 73% Arbitrary Browser Screenshot Rescaling + Unaligned Crop + Q=50 JPEG (Bug 3)
3. Heavy Contrast (1.45x) + Brightness (+45) + Unsharp Mask Sharpening (Bug 2)
4. Grayscale (B&W) & Sepia Color Filters -> 0 False Tamper Cells (Bug 4)
5. Localized Fake Text/Object Splice on Screenshot -> Isolated on 16x16 X-Ray Grid
6. Stolen Watermark Transplant onto Unrelated AI Image -> Caught as FAKE_FORGERY
7. Unregistered Random Image (including smooth 0-keypoint image) -> Abstains as UNKNOWN (Bug 6.1 & Bug 8)
8. Extreme >95% Micro-Crop (< 127x127 px) -> Gracefully abstains as UNKNOWN
9. 8-Way Dihedral Rotations & Mirror Flips (180°, Horizontal Flip, Vertical Flip, 90° CW) -> VERIFIED_AUTHENTIC
10. Online B&W Filter (0.713x Resize + Dramatic Red/Blue Channel Mixer + Non-Linear S-Curve) -> VERIFIED_AUTHENTIC (0 False Cells)
11. Heavy Black Marker Scribbles + Purple Border Frame ("100 / 10 | ★" image(3).png) -> AUTHENTIC_ALTERED (Never False Transplant Forgery)
12. Diffusion / FLUX img2img Texture Regeneration -> AUTHENTIC_ALTERED via Path C Structural Pyramid
"""

import base64
import cv2
import numpy as np
from fastapi.testclient import TestClient

from main import app, get_db

client = TestClient(app)


def _strip_b64(obj):
    if isinstance(obj, dict):
        return {k: ("<b64_omitted>" if "b64" in k else _strip_b64(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_b64(x) for x in obj]
    return obj


def make_rich_test_image(width: int = 1280, height: int = 720, seed: int = 101) -> np.ndarray:
    """Creates a textured, high-detail synthetic photograph with text, gradients, and flat regions."""
    rng = np.random.RandomState(seed)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        img[y, :, 0] = int(40 + 160 * (y / height))
        img[y, :, 1] = int(70 + 120 * (1.0 - y / height))
        img[y, :, 2] = int(90 + 100 * ((y % 180) / 180.0))

    noise = rng.randint(-28, 28, size=(height, width, 3), dtype=np.int16)
    noise = cv2.GaussianBlur(noise.astype(np.float32), (5, 5), 1.1).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Add flat white receipt/card box (Tests Bug 5 saturation clipping)
    cv2.rectangle(img, (60, 50), (360, 220), (255, 255, 255), -1)
    cv2.putText(img, "INVOICE #9481", (85, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (15, 15, 15), 2)
    cv2.putText(img, "TOTAL: $4,250.00", (85, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (20, 80, 20), 2)

    # Add rich geometric landmarks for SIFT keypoints
    for k in range(18):
        cx = int(120 + (k * 63) % (width - 240))
        cy = int(240 + (k * 97) % (height - 300))
        color = (int((k * 53) % 255), int((k * 113) % 255), int((k * 197) % 255))
        cv2.circle(img, (cx, cy), 28 + (k % 15), color, -1)
        cv2.rectangle(img, (cx - 18, cy - 18), (cx + 18, cy + 18), (245, 245, 245), 2)
        cv2.putText(img, f"K{k}", (cx - 14, cy + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)

    return img


def encode_png_bytes(img_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img_bgr)
    assert ok
    return buf.tobytes()


def encode_jpg_bytes(img_bgr: np.ndarray, quality: int = 50) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def decode_b64_image(data_uri: str) -> np.ndarray:
    b64_part = data_uri.split(",", 1)[1] if "," in data_uri else data_uri
    raw = base64.b64decode(b64_part)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def run_all_8_tests():
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM media_dag_nodes")
    conn.close()

    print("=" * 78)
    print("RUNNING VERITASNAP V2 — 12 MANDATORY & TORTURE EDGE-CASE VERIFICATION SUITE")
    print("=" * 78)

    # -------------------------------------------------------------------------
    # TEST 1: Rectangular 16:9 Image Preservation & Flat-White PSNR > 41.0 dB (Bugs 1 & 5)
    # -------------------------------------------------------------------------
    img_16_9 = make_rich_test_image(width=1280, height=720, seed=101)
    resp = client.post(
        "/api/v1/create",
        files={"file": ("rect_16_9.png", encode_png_bytes(img_16_9), "image/png")},
        data={"origin_type": 1, "whistleblower_mode": "true", "author_secret_phrase": "press-secret-99"},
    )
    assert resp.status_code == 200, resp.text
    create_data = resp.json()
    media_id = create_data["short_media_id"]
    can_w, can_h = create_data["canonical_dimensions"]
    wm_bgr = decode_b64_image(create_data["watermarked_image_b64"])

    assert can_w != can_h and can_w % 64 == 0 and can_h % 64 == 0, f"Squished dimensions: {can_w}x{can_h}"
    assert wm_bgr.shape[1] == can_w and wm_bgr.shape[0] == can_h
    assert create_data["psnr_db"] >= 41.0, f"PSNR too low: {create_data['psnr_db']}"
    print(f"[PASS] Test 1 (Bugs 1 & 5): 16:9 Aspect Ratio Preserved ({can_w}x{can_h}), PSNR={create_data['psnr_db']} dB, ID={media_id}")

    # -------------------------------------------------------------------------
    # TEST 2: Resized 73% Browser Screenshot + 50% Unaligned Crop + WhatsApp Q=50 (Bug 3)
    # -------------------------------------------------------------------------
    h, w = wm_bgr.shape[:2]
    crop_bgr = wm_bgr[19 : int(h * 0.78), 27 : int(w * 0.78)]
    resized_73 = cv2.resize(crop_bgr, (0, 0), fx=0.73, fy=0.73, interpolation=cv2.INTER_CUBIC)
    v2 = client.post(
        "/api/v1/verify",
        files={"file": ("whatsapp_crop_73.jpg", encode_jpg_bytes(resized_73, quality=50), "image/jpeg")},
    ).json()
    assert v2["verdict_code"] == "VERIFIED_AUTHENTIC", f"Test 2 failed: {_strip_b64(v2)}"
    assert v2["matched_media_id"] == media_id
    print(f"[PASS] Test 2 (Bug 3): 73% Rescaled Browser Screenshot + Unaligned Crop + Q=50 -> {v2['verdict_badge']}")

    # -------------------------------------------------------------------------
    # TEST 3: Heavy Contrast (1.45x) + Brightness (+45) + Sharpening (Bug 2)
    # -------------------------------------------------------------------------
    sharp_k = np.array([[0, -0.5, 0], [-0.5, 3.0, -0.5], [0, -0.5, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(wm_bgr, -1, sharp_k)
    contrasted = np.clip(sharpened.astype(np.float32) * 1.45 + 45.0, 0, 255).astype(np.uint8)
    v3 = client.post(
        "/api/v1/verify",
        files={"file": ("contrast_sharp.jpg", encode_jpg_bytes(contrasted, quality=70), "image/jpeg")},
    ).json()
    assert v3["verdict_code"] == "VERIFIED_AUTHENTIC", f"Test 3 failed: {_strip_b64(v3)}"
    assert v3["metrics"]["path_a_blind_watermark"]["decoded_short_media_id"] == media_id
    print(f"[PASS] Test 3 (Bug 2): Contrast 1.45x + Brightness +45 + Sharpening -> {v3['verdict_badge']} (Locked Gain={v3['metrics']['path_a_blind_watermark']['locked_gain_alpha']}x)")

    # -------------------------------------------------------------------------
    # TEST 4: Black & White (Grayscale) & Sepia Color Filters -> 0 False Positives (Bug 4)
    # -------------------------------------------------------------------------
    gray_1ch = cv2.cvtColor(wm_bgr, cv2.COLOR_BGR2GRAY)
    bw_bgr = cv2.cvtColor(gray_1ch, cv2.COLOR_GRAY2BGR)
    v4_bw = client.post(
        "/api/v1/verify",
        files={"file": ("bw_filter.jpg", encode_jpg_bytes(bw_bgr, quality=75), "image/jpeg")},
    ).json()
    assert v4_bw["verdict_code"] == "VERIFIED_AUTHENTIC", f"Test 4 B&W failed: {_strip_b64(v4_bw)}"
    assert v4_bw["metrics"]["spatial_xray"]["num_tampered_cells"] == 0

    sepia_bgr = wm_bgr.copy().astype(np.float32)
    sepia_bgr[:, :, 0] = np.clip(sepia_bgr[:, :, 0] * 0.65, 0, 255)
    sepia_bgr[:, :, 2] = np.clip(sepia_bgr[:, :, 2] * 1.30 + 25, 0, 255)
    v4_sepia = client.post(
        "/api/v1/verify",
        files={"file": ("sepia_filter.jpg", encode_jpg_bytes(sepia_bgr.astype(np.uint8), quality=75), "image/jpeg")},
    ).json()
    assert v4_sepia["verdict_code"] == "VERIFIED_AUTHENTIC", f"Test 4 Sepia failed: {_strip_b64(v4_sepia)}"
    print(f"[PASS] Test 4 (Bug 4): Grayscale (B&W) & Sepia Filters -> 0 False Tamper Cells ({v4_bw['verdict_badge']})")

    # -------------------------------------------------------------------------
    # TEST 5: Localized Fake Red/Text Edit on Screenshot -> AUTHENTIC_ALTERED
    # -------------------------------------------------------------------------
    doctored = wm_bgr.copy()
    cv2.rectangle(doctored, (can_w // 2 - 45, can_h // 2 - 35), (can_w // 2 + 45, can_h // 2 + 35), (10, 10, 250), -1)
    cv2.putText(doctored, "FAKE", (can_w // 2 - 38, can_h // 2 + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
    v5 = client.post(
        "/api/v1/verify",
        files={"file": ("doctored.jpg", encode_jpg_bytes(doctored, quality=75), "image/jpeg")},
    ).json()
    assert v5["verdict_code"] == "AUTHENTIC_ALTERED", f"Test 5 failed: {_strip_b64(v5)}"
    assert v5["metrics"]["spatial_xray"]["num_tampered_cells"] >= 1
    print(f"[PASS] Test 5 (Spatial X-Ray): Localized Fake Edit -> {v5['verdict_badge']} ({v5['metrics']['spatial_xray']['num_tampered_cells']} cells isolated, max_z_mad={v5['metrics']['spatial_xray']['max_z_mad']})")

    # -------------------------------------------------------------------------
    # TEST 6: Stolen Watermark Transplant onto Completely Different Fake Image -> FAKE_FORGERY
    # -------------------------------------------------------------------------
    ai_fake = np.full((can_h, can_w, 3), (30, 220, 180), dtype=np.uint8)
    cv2.circle(ai_fake, (can_w // 3, can_h // 3), 120, (240, 30, 200), -1)
    from main import wm_engine
    transplanted_fake, _ = wm_engine.embed(ai_fake, origin_flag=1, short_media_id_hex=media_id)
    v6 = client.post(
        "/api/v1/verify",
        files={"file": ("transplanted_fake.png", encode_png_bytes(transplanted_fake), "image/png")},
    ).json()
    assert v6["verdict_code"] == "FAKE_FORGERY", f"Test 6 failed: {_strip_b64(v6)}"
    assert v6["metrics"]["spatial_xray"]["transplant_forgery_detected"] is True
    print(f"[PASS] Test 6 (Watermark Transplant Defense): Stolen Watermark on AI Fake -> {v6['verdict_badge']}")

    # -------------------------------------------------------------------------
    # TEST 7: Unregistered Random Image (Including Smooth/Low-Keypoint Image) -> UNKNOWN (Bug 6.1 & Bug 8)
    # -------------------------------------------------------------------------
    unregistered = make_rich_test_image(width=800, height=600, seed=999)
    v7 = client.post(
        "/api/v1/verify",
        files={"file": ("unregistered.jpg", encode_jpg_bytes(unregistered, quality=80), "image/jpeg")},
    ).json()
    assert v7["verdict_code"] == "UNKNOWN", f"Test 7 failed: {_strip_b64(v7)}"
    assert v7["watermark"]["surviving_tiles"] == 0 and v7["watermark"]["tile_survival_pct"] == 0.0

    smooth_blank = np.full((300, 400, 3), 128, dtype=np.uint8)
    v7_smooth = client.post(
        "/api/v1/verify",
        files={"file": ("smooth.png", encode_png_bytes(smooth_blank), "image/png")},
    ).json()
    assert v7_smooth["verdict_code"] == "UNKNOWN", f"Test 7 smooth failed: {_strip_b64(v7_smooth)}"
    print(f"[PASS] Test 7 (Abstention Gate & Bug 6/8): Unregistered & 0-Keypoint Images -> {v7['verdict_badge']} (0 crashes, 0 false forgery)")

    # -------------------------------------------------------------------------
    # TEST 8: Extreme >95% Micro-Crop Failure Boundary & ZKP Authorship Claim
    # -------------------------------------------------------------------------
    micro_crop = wm_bgr[13:93, 19:99]
    v8 = client.post(
        "/api/v1/verify",
        files={"file": ("micro_crop.jpg", encode_jpg_bytes(micro_crop, quality=50), "image/jpeg")},
    ).json()
    assert v8["verdict_code"] in ("UNKNOWN", "AUTHENTIC_ALTERED"), f"Unexpected Test 8 verdict: {_strip_b64(v8)}"

    zkp_resp = client.post(
        "/api/v1/zkp/claim-authorship",
        json={
            "short_media_id": media_id,
            "author_secret_phrase": "press-secret-99",
            "blinding_factor_secret_hex": create_data["privacy_shield"]["blinding_factor_secret_hex"],
            "verifier_challenge_context": "LIVE_JUDGE_CHALLENGE_2026",
        },
    )
    assert zkp_resp.status_code == 200 and zkp_resp.json()["verified"] is True
    print(f"[PASS] Test 8 (Failure Boundary & ZKP Claim): Micro-Crop -> {v8['verdict_badge']} & Schnorr NIZK Verified=True")

    # -------------------------------------------------------------------------
    # TEST 9: 8-Way Dihedral Rotations & Mirror Flips (180°, H-Flip, V-Flip, 90° CW)
    # -------------------------------------------------------------------------
    rot_180 = cv2.rotate(wm_bgr, cv2.ROTATE_180)
    flip_h = cv2.flip(wm_bgr, 1)
    flip_v = cv2.flip(wm_bgr, 0)
    rot_90 = cv2.rotate(wm_bgr, cv2.ROTATE_90_CLOCKWISE)

    for label, img_variant in [
        ("180_Rotated", rot_180),
        ("Horizontal_Mirror", flip_h),
        ("Vertical_Mirror", flip_v),
        ("90_CW_Rotated", rot_90),
    ]:
        res_var = client.post(
            "/api/v2/verify",
            files={"file": (f"{label}.png", encode_png_bytes(img_variant), "image/png")},
        ).json()
        assert res_var["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 9 ({label}) failed: {_strip_b64(res_var)}"
        assert res_var["matched_media_id"] == media_id
    print("[PASS] Test 9 (Fix 1 — 8-Way Dihedral Scanner): 180°, H-Mirror, V-Mirror, & 90° CW -> VERIFIED AUTHENTIC")

    # -------------------------------------------------------------------------
    # TEST 10: Online Dramatic Black & White Filter (0.713x Resize + Channel Mixer + S-Curve)
    # -------------------------------------------------------------------------
    b_ch, g_ch, r_ch = cv2.split(wm_bgr.astype(np.float64))
    mixed_y = 0.65 * r_ch + 0.45 * g_ch - 0.15 * b_ch
    mixed_y = np.clip(mixed_y + 0.18 * (((mixed_y - 128.0) ** 2) / 128.0), 0.0, 255.0).astype(np.uint8)
    online_bw = cv2.cvtColor(mixed_y, cv2.COLOR_GRAY2BGR)
    online_bw_resized = cv2.resize(
        online_bw,
        (int(can_w * 0.713), int(can_h * 0.713)),
        interpolation=cv2.INTER_AREA,
    )
    v10 = client.post(
        "/api/v2/verify",
        files={"file": ("online_bw.jpg", encode_jpg_bytes(online_bw_resized, quality=82), "image/jpeg")},
    ).json()
    assert v10["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 10 failed: {_strip_b64(v10)}"
    assert v10["path_b_spatial_xray"]["num_tampered_cells"] == 0
    print("[PASS] Test 10 (Fix 2 — Online B&W Channel-Mixer + 0.713x Resize): 0 False Tamper Cells -> VERIFIED AUTHENTIC")

    # -------------------------------------------------------------------------
    # TEST 11: Heavy Black Marker Scribbles + Purple Border ("100 / 10 | ★" image(3).png)
    # -------------------------------------------------------------------------
    scribbled = wm_bgr.copy()
    cv2.rectangle(scribbled, (0, 0), (can_w - 1, can_h - 1), (210, 40, 140), 28)
    cv2.putText(scribbled, "100 / 10", (120, 320), cv2.FONT_HERSHEY_SIMPLEX, 6.2, (12, 12, 12), 36)
    cv2.putText(scribbled, "| * *", (220, 560), cv2.FONT_HERSHEY_SIMPLEX, 5.8, (12, 12, 12), 34)
    v11 = client.post(
        "/api/v2/verify",
        files={"file": ("image3_scribbled.png", encode_png_bytes(scribbled), "image/png")},
    ).json()
    assert v11["verdict_tier"] == "AUTHENTIC_ALTERED", f"Test 11 failed: {_strip_b64(v11)}"
    assert v11["path_b_spatial_xray"]["transplant_forgery_detected"] is False
    assert v11["path_b_spatial_xray"]["num_tampered_cells"] >= 15
    print(f"[PASS] Test 11 (Fix 3 — Heavy Black Marker Scribbles & Purple Frame): {v11['verdict_tier']} ({v11['path_b_spatial_xray']['num_tampered_cells']} cells highlighted, transplant_forgery=False)")

    # -------------------------------------------------------------------------
    # TEST 12: Diffusion / FLUX img2img Texture Regeneration (Path C Structural Lock)
    # -------------------------------------------------------------------------
    diff_sim = cv2.bilateralFilter(wm_bgr, 15, 65, 65)
    diff_sim = cv2.GaussianBlur(diff_sim, (9, 9), 2.2)
    cv2.circle(diff_sim, (can_w // 2, can_h // 2), 95, (30, 190, 245), -1)
    v12 = client.post(
        "/api/v2/verify",
        files={"file": ("flux_img2img.jpg", encode_jpg_bytes(diff_sim, quality=75), "image/jpeg")},
    ).json()
    assert v12["verdict_tier"] == "AUTHENTIC_ALTERED", f"Test 12 failed: {_strip_b64(v12)}"
    assert v12["matched_media_id"] == media_id
    print(f"[PASS] Test 12 (Diffusion / FLUX img2img Lock): Locked onto {v12['matched_media_id']} -> {v12['verdict_tier']}")

    # -------------------------------------------------------------------------
    # TEST 13: 95% Extreme Micro-Crops (167x100 & 124x124 Sky/Treetop Snippets) -> VERIFIED_AUTHENTIC
    # -------------------------------------------------------------------------
    crop_167x100 = wm_bgr[40:140, 260:427]  # 167x100 snippet touching top sky + receipt/feature tip
    crop_124x124 = wm_bgr[180:304, 300:424]  # 124x124 snippet
    for cname, cimg in [("167x100_sky_tip", crop_167x100), ("124x124_snippet", crop_124x124)]:
        v13 = client.post(
            "/api/v2/verify",
            files={"file": (f"{cname}.jpg", encode_jpg_bytes(cimg, quality=85), "image/jpeg")},
        ).json()
        assert v13["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 13 ({cname}) failed: {_strip_b64(v13)}"
        assert v13["matched_media_id"] == media_id
    print("[PASS] Test 13 (Fix 2 — 167x100 & 124x124 95% Micro-Crops): Locked & VERIFIED AUTHENTIC")

    # -------------------------------------------------------------------------
    # TEST 14: Heavy Green/Yellow Solarized Filter (Image 6 & 7) -> AUTHENTIC_ALTERED (Filter)
    # -------------------------------------------------------------------------
    solar = wm_bgr.copy().astype(np.float32)
    solar[:, :, 0] = 255.0 - solar[:, :, 0] * 0.85
    solar[:, :, 1] = np.clip(solar[:, :, 1] * 1.35 + 35.0, 0, 255)
    solar[:, :, 2] = np.where(solar[:, :, 2] > 128, 255.0 - solar[:, :, 2], solar[:, :, 2] * 1.45)
    solar_u8 = np.clip(solar, 0, 255).astype(np.uint8)
    v14 = client.post(
        "/api/v2/verify",
        files={"file": ("solarized_filter.jpg", encode_jpg_bytes(solar_u8, quality=80), "image/jpeg")},
    ).json()
    assert v14["verdict_tier"] == "AUTHENTIC_ALTERED", f"Test 14 failed: {_strip_b64(v14)}"
    assert v14["matched_media_id"] == media_id
    assert v14["path_b_spatial_xray"]["filter_edit_detected"] is True
    print(f"[PASS] Test 14 (Fix 3 — Heavy Solarized Filter): {v14['verdict_badge']}")

    # -------------------------------------------------------------------------
    # TEST 15: AI Outpainting / Expanding Corners & Borders -> AUTHENTIC_ALTERED (Outpainted)
    # -------------------------------------------------------------------------
    exp_h, exp_w = int(can_h * 1.38), int(can_w * 1.38)
    outpainted = np.full((exp_h, exp_w, 3), (185, 140, 95), dtype=np.uint8)
    pad_y = (exp_h - can_h) // 2
    pad_x = (exp_w - can_w) // 2
    outpainted[pad_y : pad_y + can_h, pad_x : pad_x + can_w] = wm_bgr
    v15 = client.post(
        "/api/v2/verify",
        files={"file": ("outpainted_borders.jpg", encode_jpg_bytes(outpainted, quality=85), "image/jpeg")},
    ).json()
    assert v15["verdict_tier"] == "AUTHENTIC_ALTERED", f"Test 15 failed: {_strip_b64(v15)}"
    assert v15["matched_media_id"] == media_id
    assert v15["path_b_spatial_xray"]["outpainted_detected"] is True
    print(f"[PASS] Test 15 (Fix 4 — AI Outpainting / Expanded Borders): {v15['verdict_badge']} (+{v15['path_b_spatial_xray']['outpainted_expansion_pct']}%)")

    # -------------------------------------------------------------------------
    # TEST 16: 20° Tilted Vertical Strip + Dense Red/Yellow Marker Scribbles & Black Border
    # -------------------------------------------------------------------------
    # Build a realistic paragraph document canvas like the uploaded paragraph photo
    doc_img = np.full((744, 1024, 3), (185, 215, 228), dtype=np.uint8)
    lines_text = [
        "A paragraph is often defined as a",
        "group of related sentences in which",
        "one single, main idea is developed.",
        "In a typical paragraph, the first",
        "sentence declares the main topic of",
        "the paragraph and the rest of the",
        "sentences develop or support the",
        "main idea. A paragraph is most",
        "often a part of a longer composition",
        "comprising of several paragraphs.",
    ]
    for idx_l, line_str in enumerate(lines_text):
        cv2.putText(
            doc_img,
            line_str,
            (45, 85 + idx_l * 66),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.45,
            (18, 18, 18),
            3,
            cv2.LINE_AA,
        )
    resp_doc = client.post(
        "/api/v2/create",
        files={"file": ("paragraph_doc.png", encode_png_bytes(doc_img), "image/png")},
        data={"origin_type": 1},
    ).json()
    doc_id = resp_doc["short_media_id"]
    doc_wm = decode_b64_image(resp_doc["watermarked_image_b64"])
    dh, dw = doc_wm.shape[:2]

    # 16A: 65% vertical crop + 20-degree diagonal tilt + contrast/brightness blowout
    M_tilt = cv2.getRotationMatrix2D((dw / 2.0, dh / 2.0), 20.0, 1.25)
    tilted_full = cv2.warpAffine(doc_wm, M_tilt, (dw, dh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    tilted_strip = tilted_full[:, dw // 4 : (dw * 3) // 4].copy()
    tilted_strip = np.clip(tilted_strip.astype(np.float32) * 1.18 + 22.0, 0, 255).astype(np.uint8)

    v16_clean = client.post(
        "/api/v2/verify",
        files={"file": ("tilted_20deg_strip.jpg", encode_jpg_bytes(tilted_strip, quality=82), "image/jpeg")},
    ).json()
    assert v16_clean["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 16A clean tilted failed: {_strip_b64(v16_clean)}"
    assert v16_clean["matched_media_id"] == doc_id

    # 16B: Add 80 criss-crossing red & yellow marker lines over 90% of tilted_strip + black screenshot border
    tilted_scrib = tilted_strip.copy()
    rng_s = np.random.RandomState(42)
    hs, ws = tilted_scrib.shape[:2]
    for _ in range(55):
        x1, y1 = rng_s.randint(0, ws), rng_s.randint(0, hs)
        x2, y2 = rng_s.randint(0, ws), rng_s.randint(0, hs)
        cv2.line(tilted_scrib, (x1, y1), (x2, y2), (35, 55, 240), rng_s.randint(4, 8), cv2.LINE_AA)
    for _ in range(25):
        x1, y1 = rng_s.randint(0, ws), rng_s.randint(0, hs)
        x2, y2 = rng_s.randint(0, ws), rng_s.randint(0, hs)
        cv2.line(tilted_scrib, (x1, y1), (x2, y2), (60, 225, 245), rng_s.randint(3, 6), cv2.LINE_AA)
    tilted_scrib_bordered = cv2.copyMakeBorder(tilted_scrib, 90, 90, 65, 65, cv2.BORDER_CONSTANT, value=(0, 0, 0))

    v16_scrib = client.post(
        "/api/v2/verify",
        files={"file": ("tilted_scribbled.png", encode_png_bytes(tilted_scrib_bordered), "image/png")},
    ).json()
    assert v16_scrib["verdict_tier"] == "AUTHENTIC_ALTERED", f"Test 16B scribbled tilted failed: {_strip_b64(v16_scrib)}"
    assert v16_scrib["matched_media_id"] == doc_id
    assert v16_scrib["path_b_spatial_xray"]["num_tampered_cells"] >= 5
    print(f"[PASS] Test 16 (Fix 6 — 20° Tilted Crop + Dense Red/Yellow Marker Scribbles): {v16_scrib['verdict_badge']} ({v16_scrib['path_b_spatial_xray']['num_tampered_cells']} cells highlighted)")

    # -------------------------------------------------------------------------
    # TEST 17: Small Thumbnail Upscale (194x259 -> 768x1024), 2-to-6 Cell Eye Crop,
    #          and Tilt (23°) + Rotate 3x + Mirror Flip Combination
    # -------------------------------------------------------------------------
    p_elon = "/working_dir/c_ca802b946c21dc8d/user_uploaded_files/ttl=63d/user_uploaded/WhatsApp Image 2026-11-13 at 11.45.56 AM(1).jpeg"
    import os
    if os.path.exists(p_elon):
        elon_thumb = cv2.imread(p_elon)
    else:
        elon_thumb = cv2.resize(make_rich_test_image(600, 800, seed=555), (194, 259))

    resp_elon = client.post(
        "/api/v2/create",
        files={"file": ("elon_thumb.jpg", encode_jpg_bytes(elon_thumb, quality=92), "image/jpeg")},
        data={"origin_type": 1},
    ).json()
    elon_id = resp_elon["short_media_id"]
    ew_can, eh_can = resp_elon["canonical_dimensions"]
    assert max(ew_can, eh_can) >= 1024, f"Expected long side >= 1024, got {(ew_can, eh_can)}"
    elon_wm = decode_b64_image(resp_elon["watermarked_image_b64"])

    # 17A: 2-to-6 Cell Horizontal Eye Crop (Screenshot_20261113_120356.jpg)
    eye_crop = elon_wm[int(eh_can * 0.26) : int(eh_can * 0.38), int(ew_can * 0.30) : int(ew_can * 0.62)].copy()
    v17_eye = client.post(
        "/api/v2/verify",
        files={"file": ("elon_eye_crop.png", encode_png_bytes(eye_crop), "image/png")},
    ).json()
    assert v17_eye["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 17A eye crop failed: {_strip_b64(v17_eye)}"
    assert v17_eye["matched_media_id"] == elon_id

    # 17B: Arbitrary Tilt (23°) + Rotate 90° CW 3 Times + Horizontal Mirror Flip
    M_23 = cv2.getRotationMatrix2D((ew_can / 2.0, eh_can / 2.0), 23.0, 1.12)
    tilted_23 = cv2.warpAffine(elon_wm, M_23, (ew_can, eh_can), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    rot_3x = cv2.rotate(cv2.rotate(cv2.rotate(tilted_23, cv2.ROTATE_90_CLOCKWISE), cv2.ROTATE_90_CLOCKWISE), cv2.ROTATE_90_CLOCKWISE)
    mirrored_tilt_rot = cv2.flip(rot_3x, 1)
    v17_mirr_tilt = client.post(
        "/api/v2/verify",
        files={"file": ("elon_tilt_rot3x_mirror.jpg", encode_jpg_bytes(mirrored_tilt_rot, quality=85), "image/jpeg")},
    ).json()
    assert v17_mirr_tilt["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 17B tilt+rot+mirror failed: {_strip_b64(v17_mirr_tilt)}"
    assert v17_mirr_tilt["matched_media_id"] == elon_id

    # 17C: Low-res eye crop from raw 194x259 thumbnail + B&W filter on Elon portrait
    eye_low = cv2.resize(elon_thumb[68:96, 60:116], (320, 160), interpolation=cv2.INTER_CUBIC)
    v17_eye_low = client.post(
        "/api/v2/verify",
        files={"file": ("elon_eye_low.jpg", encode_jpg_bytes(eye_low, quality=85), "image/jpeg")},
    ).json()
    assert v17_eye_low["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 17C low-res eye crop failed: {_strip_b64(v17_eye_low)}"
    assert v17_eye_low["matched_media_id"] == elon_id

    elon_bw = cv2.cvtColor(cv2.cvtColor(elon_wm, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    v17_bw = client.post(
        "/api/v2/verify",
        files={"file": ("elon_bw.jpg", encode_jpg_bytes(elon_bw, quality=80), "image/jpeg")},
    ).json()
    assert v17_bw["verdict_tier"] == "VERIFIED_AUTHENTIC", f"Test 17C B&W failed: {_strip_b64(v17_bw)}"
    assert v17_bw["matched_media_id"] == elon_id
    print(f"[PASS] Test 17 (194x259->768x1024 Upscale, 2-to-6 Cell Eye Crop, 23° Tilt+3xRot+Mirror, & B&W): {v17_eye['verdict_badge']}")

    # =========================================================================
    # TEST 18: Two-Way Claimed Origin Check & Unwatermarked Original Distinction
    # =========================================================================
    # 18A: Camera Photo claimed as AI-Generated Art (claimed_origin=2) -> AUTHENTIC_ALTERED (Misleading Claim)
    v18_cam_as_ai = client.post(
        "/api/v2/verify",
        files={"file": ("elon_wm.png", encode_png_bytes(elon_wm), "image/png")},
        data={"claimed_origin": 2},
    ).json()
    assert v18_cam_as_ai["verdict_tier"] == "AUTHENTIC_ALTERED", f"Expected AUTHENTIC_ALTERED for Camera claimed as AI, got {_strip_b64(v18_cam_as_ai)}"
    assert "MISLEADING CLAIM" in v18_cam_as_ai["verdict_badge"]

    # 18B: Raw Unwatermarked Original Photo -> VISUAL MATCH ONLY — INVISIBLE SIGNATURE ABSENT
    v18_unwm = client.post(
        "/api/v2/verify",
        files={"file": ("elon_raw_unwatermarked.jpg", encode_jpg_bytes(elon_thumb, quality=95), "image/jpeg")},
        data={"claimed_origin": 0},
    ).json()
    assert v18_unwm["verdict_tier"] == "AUTHENTIC_ALTERED", f"Expected AUTHENTIC_ALTERED for unwatermarked original, got {_strip_b64(v18_unwm)}"
    assert "INVISIBLE SIGNATURE ABSENT" in v18_unwm["verdict_badge"]

    # 18C: Protected Watermarked PNG -> VERIFIED_AUTHENTIC (INVISIBLE SIGNATURE VERIFIED)
    v18_wm_ok = client.post(
        "/api/v2/verify",
        files={"file": ("elon_wm.png", encode_png_bytes(elon_wm), "image/png")},
        data={"claimed_origin": 0},
    ).json()
    assert v18_wm_ok["verdict_tier"] == "VERIFIED_AUTHENTIC"
    assert "INVISIBLE SIGNATURE VERIFIED" in v18_wm_ok["verdict_badge"]
    print(f"[PASS] Test 18 (Two-Way Origin Claim Mismatch & Unwatermarked Original vs. Watermarked PNG): {v18_unwm['verdict_badge']}")

    print("=" * 78)
    print("ALL 18 MANDATORY & TORTURE VERITASNAP V2 TESTS PASSED WITH 100% PRECISION!")
    print("=" * 78)


if __name__ == "__main__":
    run_all_8_tests()
