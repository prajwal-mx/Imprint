# Imprint (VeritaSnap) — Media Provenance That Survives the Screenshot

**Problem Statement:** PS-01 — *Proof That Survives the Screenshot*  
**Team:** Horizon  
**Author:** [prajwal-mx](https://github.com/prajwal-mx)  
**License:** Apache License 2.0

---

## 1. Overview & Problem Context

Current media provenance standards fail the moment an image travels the way people actually share media online:

1. **Metadata Stripping:** Standards like C2PA store cryptographic manifests inside file headers (EXIF / JUMBF). Messaging platforms such as WhatsApp, Telegram, and Instagram strip all file headers on upload, and taking an OS screenshot creates a brand-new bitmap from screen pixels with zero file history.
2. **Crop Desynchronization:** Standard frequency-domain watermarks stretch a single payload across the entire image. Cropping even 15 to 20 pixels off the edge shifts the block grid and causes decoding to fail.
3. **The "Real Photo, Fake Edit" Paradox:** If an invisible watermark survives a screenshot, and someone edits a small region of that screenshot (such as changing a number on a receipt or drawing over a face), 95% of the background still carries the valid watermark. Global watermark detectors read the surviving background and falsely certify the doctored image as authentic.

**Imprint** addresses these three problems by combining a self-synchronizing 64x64 tiled frequency watermark, a lightweight (~28 KB per image) structural verification registry, and zero-knowledge creator privacy.

---

## 2. How It Works

### Part A: Protecting an Original Photo (`POST /api/v1/create`)

1. **Metadata Scrubbing and Aspect-Ratio Framing**
   All embedded EXIF, GPS, and camera serial headers are stripped by re-encoding from raw pixel buffers. The image is normalized so its dimensions `(W_can, H_can)` are exact multiples of 64 pixels while preserving the original aspect ratio.

2. **Creator Attribution and Zero-Knowledge Privacy Mode**
   - **Public Mode:** Records the creator's handle and optional capture location.
   - **Private (Whistleblower) Mode:** Stores zero personal information or GPS data. Instead, the creator's secret passphrase and the photo's ID are bound into a 2048-bit prime **Pedersen Commitment** (`C = g^s * h^r mod p`, RFC 3526 Group 14). The creator can later prove authorship using a non-interactive **Schnorr Zero-Knowledge Proof** without exposing their passphrase.

3. **In-Pixel 64-Bit Tiled Watermark (Y Channel DWT-LL + 8x8 DCT + STDM)**
   Every 64x64 pixel square across the luminance (`Y`) channel independently embeds the same 64-bit packet:
   - **Bits 0..3 (4 bits):** Origin Type (`0001` Hardware Camera, `0010` AI Generator, `0011` Edited Version, `0100` Private Capture).
   - **Bits 4..47 (44 bits):** Unique `short_media_id` (`2^44`, about 17.5 trillion unique IDs).
   - **Bits 48..63 (16 bits):** Systematic **Extended BCH(64, 48, d_min = 6)** error-correction parity bits.
   - **Embedding Domain:** 1-level 2D Haar Wavelet Transform (`LL` low-frequency subband) partitioned into sixteen 8x8 Orthonormal Type-II DCT blocks, using **Spread-Transform Dither Modulation (STDM)** across 12 mid-low AC coordinates (`Delta = 22.0`) plus a bandpass periodic synchronization pilot. Visual quality remains above **43 dB PSNR** (average change of about 1.17 brightness levels out of 255).

4. **Lightweight Structural Fingerprint (~28 KB in SQLite)**
   Instead of requiring the full raw image for verification, the registry stores:
   - A compressed **16x16x18 Structural Summary Grid** (~8 KB: 4x4 luminance structure plus 2 chrominance means per cell).
   - Compressed multi-scale **SIFT landmark coordinates and descriptors** (~16 KB).
   - A 64-byte **Ed25519 digital signature** over the manifest and an optional `parent_media_id` link to track edit history.

### Part B: Verifying a Screenshot or Edited Image (`POST /api/v1/verify`)

1. **8-Way Orientation and Mirror Recovery**
   Scans all 8 dihedral symmetries (0, 90, 180, 270 degrees, normal and mirrored) via Fast Fourier Transform synchronization peaks and Sobel edge correlation, snapping rotated or mirrored images upright in under 8 ms.

2. **Path A: Blind Modulo-64 Sync and Multi-Gain Soft Decoding**
   - Folds the high-pass luminance residual modulo 64 and runs 2D FFT circular cross-correlation to find the exact `(dy, dx)` crop offset in about 0.3 ms.
   - Sweeps 39 contrast and sharpness gain multipliers (`alpha` in `[0.40, 2.30]`) in vectorized NumPy and sums continuous Log-Likelihood Ratios across all surviving 64x64 tiles into a **Chase-2 soft-decision BCH decoder** (correcting up to 5 bit flips).

3. **Path B and Path C: Geometric and Edge-Silhouette Alignment**
   If browser zoom, an angled phone-camera screen capture, or heavy cropping has shifted the scale, **SIFT + USAC_MAGSAC homography**, paired with a multi-scale CLAHE and Sobel edge pyramid matcher, warps the query back into the original `(W_can, H_can)` coordinate frame.

4. **16x16 Spatial Change Map and Context Reconstruction**
   - Calibrates global brightness, contrast, and color filters (including 3-channel regression for black-and-white filters) using Interquartile Range statistics.
   - Computes the **Median Absolute Deviation Z-Score** across all visible cells in the 16x16 grid. Cells with `Z_MAD > 4.5` are highlighted as localized post-capture edits, while cropped-out areas or AI-expanded (outpainted) borders are reconstructed on the visual map.

---

## 3. Verdict Categories

Imprint maps low-level signal and cryptographic telemetry into clear, plain-English verdicts:

| Verdict | When It Triggers | What the User Sees |
| :--- | :--- | :--- |
| **Authentic Photo (Signature Verified)** | Embedded 64x64 pixel signature and Ed25519 signature are valid, with 0 localized tampered cells. | Confirms origin, creator/privacy status, and lists survived transformations (crop %, flip, compression). |
| **Visual Match (Signature Absent)** | Visual structure matches a registered photo with 0 edits, but the 64x64 pixel signature is missing (`Z < 3.4`). | Distinguishes the raw unwatermarked source file (or a copy stripped by a watermark remover) from a signed file. |
| **Original Source Found: Edited** | Provenance matches a registered capture, but one or more cells in the 16x16 grid were modified, borders were expanded with AI, or a heavy artistic filter was applied. | Highlights exact modified regions and shows the original frame context. |
| **Confirmed Fake / Forgery** | A stolen watermark was transplanted onto an unrelated image, the Ed25519 signature failed, or an AI image is falsely claimed as a camera photo. | Alerts the user that the signature or origin claim is forged. |
| **Unverified (No History Found)** | Neither a surviving pixel signature nor a structural match exists in the archive. | Clearly states that missing history does not prove an image is fake. |

---

## 4. Documented Failure Cases and Empirical Boundaries

| Transformation / Attack | Tested Regime | Behavior and Mechanism |
| :--- | :--- | :--- |
| **OS Screenshots and WhatsApp Compression** | JPEG quality `Q = 95` down to `Q = 25` | **Survives 100%:** DWT-LL 8x8 DCT blocks span 16x16 spatial pixels, remaining above JPEG quantization step sizes down to `Q = 25`. |
| **Unaligned Cropping** | Up to 80% to 85% of image area removed | **Survives 100%:** Modulo-64 torus folding and soft LLR accumulation across remaining tiles recover the 64-bit codeword with 0% post-ECC BER. |
| **Rotations, Tilts, and Mirror Flips** | 90, 180, 270 degrees, horizontal/vertical mirror, and 20 to 35 degree tilts | **Survives 100%:** 8-way dihedral scanner and normal/mirrored SIFT homography rectify geometry before tile extraction. |
| **Brightness, Contrast, and B&W Filters** | Brightness plus or minus 50, contrast 0.5x to 2.0x, grayscale, sepia | **Survives 100%:** DC brightness offsets cancel in AC DCT bands; 39-step gain lock recovers contrast scaling; 3-channel regression prevents false tamper flags on B&W filters. |
| **Localized Edits and AI Outpainting** | Marker scribbles, text edits, splices, AI border expansion (+15% to +85%) | **Detected and localized:** Isolates edited cells via MAD outlier thresholding (`Z_MAD > 4.5`) and highlights added outer borders. |
| **Failure Boundary 1: Extreme Tiny Crops** | More than 95% area removed (fragment smaller than 100x100 px on featureless sky/background) | **Documented breaking point:** By the pigeonhole principle, an unaligned crop smaller than 127x127 px is not guaranteed to contain a single complete 64x64 tile, and featureless patches lack SIFT landmarks. The system safely outputs **No History Found**. |
| **Failure Boundary 2: Severe Pixel Destruction** | JPEG quality `Q <= 10` or Gaussian noise `sigma >= 15` | **Documented breaking point:** Quantization noise exceeds `Delta / sqrt(3)` (about 12.7), collapsing the STDM dither bins. Path B visual matching continues down to `Q = 10` on structured scenes; otherwise the system safely abstains. |
| **Failure Boundary 3: Heavy Occlusion plus Off-Axis Tilt** | Simultaneous 20 degree diagonal tilt, 65% crop, and more than 85% dense marker scribble occlusion | **Documented breaking point:** When an image is tilted off-grid and more than 85% of underlying edges are covered by scribbles, homography inliers drop below the safety threshold (fewer than 10), causing the system to abstain rather than guess. |

---

## 5. Time Complexity and Storage Footprint

- **Embedding complexity:** `O(N)` linear in pixel count `N = W x H` (about 18 ms on CPU using vectorized 3D NumPy BLAS matrix multiplication).
- **Verification complexity:** `O(N + T^2 log T)`, effectively `O(N)` linear time (about 35 to 60 ms on CPU). The 2D FFT sync search operates on a fixed 64x64 folded grid (0.3 ms), Chase-2 BCH decoding runs in `O(1)` table lookup time (0.15 ms), and the SQLite lookup by 44-bit ID is `O(1)` on the primary key index.
- **Database footprint:** About 28 KB of mathematical fingerprint data per registered image, plus an optional compressed preview thumbnail for the Archive viewer.

---

## 6. Repository Structure

```text
.
├── Dockerfile                       # Multi-stage Railway build (Node + Python)
├── .dockerignore
├── railway.json                     # Railway Dockerfile deployment config
├── veritasnap-backend/
│   ├── main.py                      # FastAPI application and provenance pipeline
│   ├── requirements.txt
│   ├── test_all_edge_cases.py       # 18-test verification suite
│   ├── db/schema.sql
│   └── veritasnap/
│       ├── watermark_engine.py      # DWT-LL + DCT + STDM watermark
│       ├── spatial_xray.py          # Sync recovery, alignment, tamper map
│       └── crypto_dag_zkp.py        # Ed25519 manifests and ZK proofs
└── veritasnap-frontend/
    ├── index.html
    ├── package.json
    ├── package-lock.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── index.css
        └── main.jsx
```

---

## 7. Local Setup and Running the Project

### Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer

### 1. Start the Backend (`veritasnap-backend/`)

```bash
cd veritasnap-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the automated 18-test verification suite
python3 test_all_edge_cases.py

# Launch FastAPI on http://127.0.0.1:8000
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start the Frontend (`veritasnap-frontend/`)

```bash
cd veritasnap-frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. The Vite development server proxies `/api` requests to `http://localhost:8000`.

### 3. Production build (single service)

```bash
cd veritasnap-frontend
npm ci
npm run build
cd ../veritasnap-backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

When `veritasnap-frontend/dist` exists, the FastAPI backend serves the built React application at `/` and keeps the API under `/api`.

---

## 8. Railway Deployment

The repository is configured for a single-service Railway deployment using the root `Dockerfile`.

1. Create a Railway project and deploy from this GitHub repository.
2. Railway reads `railway.json` and builds the Dockerfile. No build command or root directory override is required.
3. The container builds the React frontend in a Node stage, installs the Python dependencies, and serves both the API and the built UI from FastAPI on Railway's assigned `PORT`.

### Persistence

The SQLite registry lives at `veritasnap_registry.db` inside the backend working directory by default. Railway containers use ephemeral storage, so the archive resets on each redeploy. To persist registrations across deployments:

1. Attach a Railway volume mounted at `/data`.
2. Set the environment variable `VERITASNAP_DB_PATH=/data/veritasnap_registry.db`.

No other environment variables or secrets are required for the demo. The frontend uses same-origin API requests in production. If the frontend is hosted separately, set `VITE_API_BASE` to the backend origin at build time (see `veritasnap-frontend/.env.example`).

---

## 9. API Summary

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/v1/registry` | List registered media and archive statistics |
| `POST` | `/api/v1/create` | Scrub metadata, embed the 64-bit watermark, sign, and register an image |
| `POST` | `/api/v1/verify` | Verify a screenshot or edited image and return the verdict plus tamper map |
| `POST` | `/api/v1/zkp/claim-authorship` | Prove authorship of a private capture without revealing the passphrase |
| `GET` | `/api/v1/benchmark/run` | Run the built-in transformation benchmark |
| `POST` | `/api/v1/registry/reset` | Clear the local registry and social feed |

Version 2 aliases (`/api/v2/...`) are also exposed for the same core routes.

Interactive API documentation is available at `/docs` when the backend is running.

---

## 10. Privacy and Security Notes

- EXIF, GPS, and camera serial metadata are removed from every processed image before storage.
- Private mode stores no creator identity or location. Authorship is bound to a Pedersen commitment and can be proven with a Schnorr zero-knowledge proof.
- The repository contains no credentials, API keys, or environment files. The SQLite database is generated at runtime and is excluded from version control.
- The demo registry is intentionally local and unauthenticated. For a production deployment, place the API behind authentication, restrict CORS, and use a managed database.

---

## 11. License

Licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) for the full text.

Copyright 2026 Prajwal (prajwal-mx).
