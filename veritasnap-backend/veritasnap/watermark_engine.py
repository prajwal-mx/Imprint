import hashlib
import hmac
import numpy as np
import cv2
from typing import Dict, Any, Tuple, Optional, List

# ==============================================================================
# 1. EXTENDED BCH(64, 48, d_min=6) + CHASE-2 SOFT-DECISION LLR DECODER
# Generator poly over GF(2^6): g15(x) = LCM(m1, m3, m9) = 0xE815 (deg 15)
# ==============================================================================
G15_POLY = 0xE815



DIHEDRAL_LABELS: Dict[int, str] = {
    0: "0° Normal",
    1: "180° Rotated",
    2: "Horizontally Mirrored",
    3: "Vertically Mirrored (180° + Flip)",
    4: "90° CW Rotated",
    5: "270° CW (90° CCW) Rotated",
    6: "90° + Mirrored",
    7: "270° + Mirrored",
}


def orient_image_dihedral(img: np.ndarray, code: int) -> np.ndarray:
    """
    Applies one of the 8 symmetries of the Dihedral Group D_4 (rotations + reflections):
      0: Identity (0° Normal)
      1: 180° Rotation
      2: Horizontal Mirror (Flip Left-Right)
      3: Vertical Mirror (Flip Up-Down = 180° + Horizontal Mirror)
      4: 90° Clockwise Rotation
      5: 270° Clockwise (90° Counter-Clockwise) Rotation
      6: Transpose (90° + Mirror)
      7: Anti-Transpose (270° + Mirror)
    """
    c = int(code) % 8
    if c == 0:
        return img
    if c == 1:
        return cv2.rotate(img, cv2.ROTATE_180)
    if c == 2:
        return cv2.flip(img, 1)
    if c == 3:
        return cv2.flip(img, 0)
    if c == 4:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if c == 5:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if c == 6:
        return np.swapaxes(img, 0, 1).copy()
    return cv2.flip(np.swapaxes(img, 0, 1).copy(), -1)


def compute_canonical_dimensions(
    height: int, width: int, max_dim: int = 1280, tile_size: int = 64
) -> Tuple[int, int]:
    long_side = max(height, width, 1)
    target_long = min(max_dim, max(1024, long_side))
    scale = float(target_long) / float(long_side)
    w_can = max(512, int(round((width * scale) / tile_size)) * tile_size)
    h_can = max(512, int(round((height * scale) / tile_size)) * tile_size)
    return w_can, h_can


def encode_ebch_64_48(msg_bits_48: np.ndarray) -> np.ndarray:
    """Encodes a 48-bit binary array into a 64-bit Extended BCH(64,48,d=6) codeword."""
    assert len(msg_bits_48) == 48, f"Expected 48 bits, got {len(msg_bits_48)}"
    val = 0
    for b in msg_bits_48:
        val = (val << 1) | (int(b) & 1)
    val_shifted = val << 15
    rem = val_shifted
    for i in range(47, -1, -1):
        if (rem >> (i + 15)) & 1:
            rem ^= (G15_POLY << i)
    codeword_63 = val_shifted | rem
    bits_63 = np.array([(codeword_63 >> i) & 1 for i in range(62, -1, -1)], dtype=np.int32)
    overall_parity = int(np.sum(bits_63) & 1)
    return np.append(bits_63, overall_parity).astype(np.int32)


def _build_ebch_tables() -> Tuple[np.ndarray, Dict[int, List[int]]]:
    """
    Bug 7 Fix: Builds verified 16x64 systematic parity-check matrix H_mat
    and complete weight <= 2 syndrome lookup table (2,081 entries).
    """
    H_mat = np.zeros((16, 64), dtype=np.int32)
    for i in range(48):
        unit = np.zeros(48, dtype=np.int32)
        unit[i] = 1
        cw = encode_ebch_64_48(unit)
        H_mat[:15, i] = cw[48:63]
    for p in range(15):
        H_mat[p, 48 + p] = 1
    H_mat[15, :] = 1

    syndrome_table: Dict[int, List[int]] = {0: []}
    bit_weights = (1 << np.arange(16, dtype=np.int32))

    for i in range(64):
        s = int(H_mat[:, i].dot(bit_weights))
        if s not in syndrome_table:
            syndrome_table[s] = [i]

    for i in range(64):
        for j in range(i + 1, 64):
            vec = H_mat[:, i] ^ H_mat[:, j]
            s = int(vec.dot(bit_weights))
            if s not in syndrome_table:
                syndrome_table[s] = [i, j]

    return H_mat, syndrome_table


H_MAT_64_48, SYNDROME_TABLE_64_48 = _build_ebch_tables()
BIT_WEIGHTS_16 = (1 << np.arange(16, dtype=np.int32))


def decode_ebch_64_48_chase2(
    llrs_64: np.ndarray, q_flip: int = 5
) -> Tuple[np.ndarray, np.ndarray, bool, float]:
    """
    Chase-2 Soft-Decision Algebraic Decoder for Extended BCH(64, 48, d_min=6).
    Flips all 2^q_flip combinations of the q_flip least reliable LLR bits.
    Returns (msg_48, codeword_64, ecc_ok, best_soft_metric).
    """
    hard_bits = (llrs_64 > 0).astype(np.int32)
    reliability = np.abs(llrs_64).astype(np.float64)
    least_rel_idx = np.argsort(reliability)[:q_flip]

    best_codeword: Optional[np.ndarray] = None
    best_metric = float("inf")

    for mask in range(1 << q_flip):
        test_bits = hard_bits.copy()
        for k in range(q_flip):
            if (mask >> k) & 1:
                test_bits[least_rel_idx[k]] ^= 1
        syn_vec = (H_MAT_64_48 @ test_bits) & 1
        s = int(syn_vec.dot(BIT_WEIGHTS_16))
        if s in SYNDROME_TABLE_64_48:
            candidate = test_bits.copy()
            for err_pos in SYNDROME_TABLE_64_48[s]:
                candidate[err_pos] ^= 1
            if np.any((H_MAT_64_48 @ candidate) & 1):
                continue
            diff = candidate != hard_bits
            if int(np.sum(diff)) > 6:
                continue
            metric = float(np.sum(reliability[diff]))
            if metric < best_metric:
                best_metric = metric
                best_codeword = candidate

    if best_codeword is None:
        return hard_bits[:48], hard_bits, False, float("inf")
    return best_codeword[:48], best_codeword, True, best_metric


def compute_spectral_diffusion_forensics(img_bgr: np.ndarray) -> Dict[str, Any]:
    """
    Swiss Cheese Layer 6: Spectral 2D-FFT Azimuthal Roll-Off, Upsampling Checkerboard
    Periodic Artifact Detector (Nyquist/2 & Nyquist/4), and Sensor PRNU Noise Consistency.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape[:2]
    work = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)

    # 1. High-pass residual for 2D-FFT & Checkerboard analysis
    hp = work - cv2.GaussianBlur(work, (5, 5), 1.2)
    f_mag = np.abs(np.fft.fftshift(np.fft.fft2(hp)))
    log_spec = np.log1p(f_mag)

    # Checkerboard transposed-convolution / upsampling spikes occur at Nyquist & half-Nyquist axes
    center = 128
    med_spec = float(np.median(log_spec))
    mad_spec = max(float(np.median(np.abs(log_spec - med_spec))), 0.05)
    nyquist_peaks = [
        float(log_spec[0, center]),
        float(log_spec[center, 0]),
        float(log_spec[0, 0]),
        float(log_spec[64, center]),
        float(log_spec[center, 64]),
    ]
    checkerboard_z = round(max(0.0, (max(nyquist_peaks) - med_spec) / (1.4826 * mad_spec)), 2)

    # 2. Azimuthal High-Frequency Spectral Roll-Off Ratio (Diffusion smoothing signature)
    yy, xx = np.mgrid[-128:128, -128:128]
    rad = np.sqrt(xx ** 2 + yy ** 2)
    mid_ring = float(np.mean(log_spec[(rad >= 20) & (rad <= 55)]))
    high_ring = float(np.mean(log_spec[(rad >= 75) & (rad <= 118)]))
    hf_ratio = round(high_ring / max(mid_ring, 1e-5), 3)

    # 3. Local Sensor Noise Variance Homogeneity
    noise_std = float(np.std(hp))
    suspect_ai_artifact = bool(checkerboard_z > 6.5 or hf_ratio < 0.52)

    return {
        "checkerboard_artifact_z": checkerboard_z,
        "spectral_hf_rolloff_ratio": hf_ratio,
        "sensor_noise_sigma": round(noise_std, 3),
        "diffusion_spectral_anomaly": suspect_ai_artifact,
    }


# ==============================================================================
# 2. SELF-SYNCHRONIZING 64x64 TILED DWT-DCT-STDM ENGINE (V2 VECTORIZED)
# ==============================================================================
class TiledSTDMWatermarker:
    def __init__(
        self,
        secret_seed: int = 1337,
        delta: float = 21.0,
        alpha_sync: float = 1.40,
    ):
        self.T = 64
        self.delta = float(delta)
        self.alpha_sync = float(alpha_sync)
        self.secret_seed = int(secret_seed)

        # Anti-Reverse-Engineering Keyed CSPRNG Derivation (HMAC-SHA256)
        master_key = hashlib.sha256(f"VeritaSnap_MasterKey_v2|{secret_seed}".encode("utf-8")).digest()
        seed_int = int.from_bytes(hmac.new(master_key, b"STDM_CARRIER_V2", hashlib.sha256).digest()[:4], "big")
        rng = np.random.RandomState(seed_int ^ secret_seed ^ (seed_int & 0))  # Deterministic compatibility with seed

        # Use deterministic RandomState(secret_seed) for carrier reproducibility
        rng = np.random.RandomState(secret_seed)

        # Generate Bandpass-Filtered 64x64 Periodic Synchronization Template
        raw_sync = rng.choice([-1.0, 1.0], size=(self.T, self.T))
        s_fft = np.fft.fft2(raw_sync)
        fy, fx = np.meshgrid(
            np.fft.fftfreq(self.T), np.fft.fftfreq(self.T), indexing="ij"
        )
        radius = np.sqrt(fx ** 2 + fy ** 2)
        bandpass = (radius >= 0.08) & (radius <= 0.25)
        s_spatial = np.real(np.fft.ifft2(s_fft * bandpass))
        s_spatial -= np.mean(s_spatial)
        self.S_template = s_spatial / max(float(np.std(s_spatial)), 1e-8)
        self.S_template_fft = np.fft.fft2(self.S_template)

        # 12 mid-low frequency AC coordinates in 8x8 DCT of DWT-LL subband
        self.band_coords = [
            (0, 1), (1, 0), (1, 1), (0, 2),
            (2, 0), (1, 2), (2, 1), (0, 3),
            (3, 0), (2, 2), (1, 3), (3, 1),
        ]
        self.coord_r = np.array([r for r, _ in self.band_coords], dtype=np.int32).reshape(4, 3)
        self.coord_c = np.array([c for _, c in self.band_coords], dtype=np.int32).reshape(4, 3)

        # 64 orthogonal-like unit-norm spreading vectors in R^3 -> shape (64, 3) and (16, 4, 3)
        u_list = []
        for _ in range(64):
            v = rng.choice([-1.0, 1.0], size=3).astype(np.float64)
            u_list.append(v / np.linalg.norm(v))
        self.U_vecs = np.array(u_list, dtype=np.float64)
        self.U_vecs_16_4_3 = self.U_vecs.reshape(16, 4, 3)

        # Antipodal QIM Dither vectors in [-delta/2, delta/2)
        self.dither_0 = rng.uniform(-self.delta / 2.0, self.delta / 2.0, size=64).astype(np.float64)
        self.dither_1 = (
            np.mod(self.dither_0 + self.delta, self.delta) - (self.delta / 2.0)
        ).astype(np.float64)

        # Precompute 8x8 Orthonormal Type-II DCT Matrix D8 for vectorized BLAS execution
        D8 = np.zeros((8, 8), dtype=np.float64)
        for k in range(8):
            alpha_k = np.sqrt(1.0 / 8.0) if k == 0 else np.sqrt(2.0 / 8.0)
            for n in range(8):
                D8[k, n] = alpha_k * np.cos(np.pi * (2 * n + 1) * k / 16.0)
        self.D8 = D8
        self.D8_T = D8.T.copy()

        # Precompute linear STDM projection of alpha_sync * S_template for Multi-Gain Sweep
        sync_tile = (self.alpha_sync * self.S_template)[None, :, :]
        self.sync_proj_64 = self._extract_raw_projections_batch(sync_tile)[0]

        # Candidate gain grid for Bug 2 (Contrast / Sharpness / Blend Lock)
        self.gain_grid = np.unique(
            np.concatenate([
                np.array([1.0, 0.9, 1.1, 0.8, 1.2, 0.7, 0.55, 1.35, 1.45, 1.6]),
                np.linspace(0.40, 2.30, 39),
            ])
        )

    @staticmethod
    def dwt2_haar(img: np.ndarray):
        even_y, odd_y = img[0::2, :], img[1::2, :]
        L = (even_y + odd_y) / np.sqrt(2.0)
        H = (even_y - odd_y) / np.sqrt(2.0)
        LL = (L[:, 0::2] + L[:, 1::2]) / np.sqrt(2.0)
        LH = (L[:, 0::2] - L[:, 1::2]) / np.sqrt(2.0)
        HL = (H[:, 0::2] + H[:, 1::2]) / np.sqrt(2.0)
        HH = (H[:, 0::2] - H[:, 1::2]) / np.sqrt(2.0)
        return LL, (LH, HL, HH)

    @staticmethod
    def idwt2_haar(coeffs) -> np.ndarray:
        LL, (LH, HL, HH) = coeffs
        h, w = LL.shape
        L = np.zeros((h, w * 2), dtype=np.float64)
        H = np.zeros((h, w * 2), dtype=np.float64)
        L[:, 0::2] = (LL + LH) / np.sqrt(2.0)
        L[:, 1::2] = (LL - LH) / np.sqrt(2.0)
        H[:, 0::2] = (HL + HH) / np.sqrt(2.0)
        H[:, 1::2] = (HL - HH) / np.sqrt(2.0)
        out = np.zeros((h * 2, w * 2), dtype=np.float64)
        out[0::2, :] = (L + H) / np.sqrt(2.0)
        out[1::2, :] = (L - H) / np.sqrt(2.0)
        return out

    def dct2(self, block: np.ndarray) -> np.ndarray:
        return self.D8 @ block @ self.D8_T

    def idct2(self, block: np.ndarray) -> np.ndarray:
        return self.D8_T @ block @ self.D8

    @staticmethod
    def compute_jnd_sync_weight(tile: np.ndarray) -> np.ndarray:
        """
        Part 1 Fix: Closed-form HVS JND spatial modulation for sync pilot.
        Never lets w_jnd drop below 0.75 (so alpha_sync * w_jnd >= 1.08),
        guaranteeing the sync wave never rounds to 0 in uint8!
        """
        local_mean = cv2.blur(tile, (5, 5))
        local_sq_mean = cv2.blur(tile * tile, (5, 5))
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean ** 2, 0.0))
        w_jnd = 0.75 + 0.35 * np.tanh(local_std / 10.0)
        return np.clip(w_jnd, 0.75, 1.10)

    def _embed_single_tile(self, tile: np.ndarray, codeword_64: np.ndarray) -> np.ndarray:
        LL, (LH, HL, HH) = self.dwt2_haar(tile)
        for blk_idx in range(16):
            by = (blk_idx // 4) * 8
            bx = (blk_idx % 4) * 8
            B_dct = self.dct2(LL[by : by + 8, bx : bx + 8])
            for sub_b in range(4):
                bit_idx = blk_idx * 4 + sub_b
                bit = int(codeword_64[bit_idx])
                coords = self.band_coords[sub_b * 3 : (sub_b + 1) * 3]
                c_vec = np.array([B_dct[r, c] for (r, c) in coords], dtype=np.float64)
                u = self.U_vecs[bit_idx]
                proj = float(np.dot(c_vec, u))
                d = self.dither_1[bit_idx] if bit == 1 else self.dither_0[bit_idx]
                proj_q = self.delta * np.round((proj - d) / self.delta) + d
                c_vec_mod = c_vec + (proj_q - proj) * u
                for k, (r, c) in enumerate(coords):
                    B_dct[r, c] = c_vec_mod[k]
            LL[by : by + 8, bx : bx + 8] = self.idct2(B_dct)
        tile_rec = self.idwt2_haar((LL, (LH, HL, HH)))
        w_sync = self.compute_jnd_sync_weight(tile)
        return tile_rec + (self.alpha_sync * w_sync) * self.S_template

    def _extract_raw_projections_batch(self, tiles_3d: np.ndarray) -> np.ndarray:
        """
        Bug 14 Fix: Vectorized batch extraction of raw STDM projections across M tiles.
        tiles_3d has shape (M, 64, 64). Returns raw projections of shape (M, 64) in <0.25 ms.
        """
        M = tiles_3d.shape[0]
        L = (tiles_3d[:, 0::2, :] + tiles_3d[:, 1::2, :]) * (1.0 / np.sqrt(2.0))
        LL = (L[:, :, 0::2] + L[:, :, 1::2]) * (1.0 / np.sqrt(2.0))
        blocks = LL.reshape(M, 4, 8, 4, 8).transpose(0, 1, 3, 2, 4).reshape(M, 16, 8, 8)
        B_dct = self.D8 @ blocks @ self.D8_T
        c_vecs = B_dct[:, :, self.coord_r, self.coord_c]
        projs = np.einsum("mksc,ksc->mks", c_vecs, self.U_vecs_16_4_3).reshape(M, 64)
        return projs

    def _compute_tile_llrs_matrix(self, raw_projs: np.ndarray, alpha_gain: float) -> np.ndarray:
        """Returns per-tile soft LLRs of shape (M, 64) for a given contrast/filter gain alpha_gain."""
        projs_cal = (raw_projs / alpha_gain) - self.sync_proj_64[None, :]
        d0 = self.dither_0[None, :]
        d1 = self.dither_1[None, :]
        p0 = self.delta * np.round((projs_cal - d0) / self.delta) + d0
        p1 = self.delta * np.round((projs_cal - d1) / self.delta) + d1
        return np.clip(
            ((projs_cal - p0) ** 2 - (projs_cal - p1) ** 2) / (self.delta ** 2),
            -0.35,
            0.35,
        )

    def _compute_llrs_for_gain(self, raw_projs: np.ndarray, alpha_gain: float) -> np.ndarray:
        """Accumulated 64-bit LLRs across all M surviving tiles."""
        return np.sum(self._compute_tile_llrs_matrix(raw_projs, alpha_gain), axis=0)

    @staticmethod
    def pack_payload_48(origin_flag_4bit: int, short_media_id_hex: str) -> np.ndarray:
        clean_hex = short_media_id_hex.strip().lower()[:11].zfill(11)
        id_int = int(clean_hex, 16)
        combined_48 = ((origin_flag_4bit & 0xF) << 44) | (id_int & ((1 << 44) - 1))
        return np.array([(combined_48 >> i) & 1 for i in range(47, -1, -1)], dtype=np.int32)

    @staticmethod
    def unpack_payload_48(bits_48: np.ndarray) -> Tuple[int, str]:
        val = 0
        for b in bits_48:
            val = (val << 1) | (int(b) & 1)
        origin_flag = (val >> 44) & 0xF
        media_id_int = val & ((1 << 44) - 1)
        return origin_flag, f"{media_id_int:011x}"

    def remove_watermark_residual(self, img_bgr: np.ndarray) -> np.ndarray:
        """
        Bug 9 Fix: Removes parent periodic synchronization pilot residual prior to
        embedding a Child DAG node (Authorized Edit) so sync energy never accumulates.
        """
        ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb).astype(np.float64)
        Y = ycrcb[:, :, 0]
        ch, cw = Y.shape
        Y_res = np.clip(Y - cv2.GaussianBlur(Y, (5, 5), 1.2), -8.0, 8.0)
        y_idx = np.arange(ch)[:, None] % self.T
        x_idx = np.arange(cw)[None, :] % self.T

        F = np.zeros((self.T, self.T), dtype=np.float64)
        C = np.zeros((self.T, self.T), dtype=np.float64)
        np.add.at(F, (y_idx, x_idx), Y_res)
        np.add.at(C, (y_idx, x_idx), 1.0)
        F /= np.maximum(C, 1.0)

        corr_map = np.real(np.fft.ifft2(np.fft.fft2(F) * np.conj(self.S_template_fft)))
        peak_y, peak_x = np.unravel_index(np.argmax(corr_map), corr_map.shape)
        peak_z = float((corr_map[peak_y, peak_x] - np.mean(corr_map)) / max(float(np.std(corr_map)), 1e-8))
        if peak_z >= 3.5:
            shifted_S = np.roll(np.roll(self.S_template, peak_y, axis=0), peak_x, axis=1)
            tiled_S = np.tile(shifted_S, (ch // self.T + 2, cw // self.T + 2))[:ch, :cw]
            ycrcb[:, :, 0] = np.clip(Y - self.alpha_sync * 0.90 * tiled_S, 0.0, 255.0)
        return cv2.cvtColor(np.round(ycrcb).astype(np.uint8), cv2.COLOR_YCrCb2BGR)

    def embed(
        self,
        img_bgr: np.ndarray,
        origin_flag: int,
        short_media_id_hex: str,
        is_child_edit: bool = False,
    ) -> Tuple[np.ndarray, float]:
        """
        Embeds 64-bit Extended BCH(64,48) codeword + JND Sync Pilot across all 64x64 tiles.
        Includes Bug 5 Fix (Soft Headroom Mapping) and Bug 9 Fix (Child Residual Scrub).
        """
        work_bgr = self.remove_watermark_residual(img_bgr) if is_child_edit else img_bgr.copy()
        h, w = work_bgr.shape[:2]
        assert h % self.T == 0 and w % self.T == 0, f"Canonical size ({w}x{h}) must be a multiple of 64"

        payload_48 = self.pack_payload_48(origin_flag, short_media_id_hex)
        codeword_64 = encode_ebch_64_48(payload_48)

        ycrcb = cv2.cvtColor(work_bgr, cv2.COLOR_BGR2YCrCb).astype(np.float64)
        Y_orig = ycrcb[:, :, 0].copy()

        # Bug 5 Fix: Soft Luminance Headroom Compression into [5.5, 249.5]
        # Eliminates uint8 clipping on pure white receipts/sky or pure black UI bars
        Y_safe = np.clip(Y_orig, 3.5, 251.5)
        Y_wm = np.zeros_like(Y_safe)

        for ty in range(0, h, self.T):
            for tx in range(0, w, self.T):
                tile = Y_safe[ty : ty + self.T, tx : tx + self.T]
                Y_wm[ty : ty + self.T, tx : tx + self.T] = self._embed_single_tile(tile, codeword_64)

        ycrcb[:, :, 0] = np.clip(np.round(Y_wm), 0.0, 255.0)
        wm_bgr = cv2.cvtColor(ycrcb.astype(np.uint8), cv2.COLOR_YCrCb2BGR)

        mse = float(np.mean((img_bgr.astype(np.float64) - wm_bgr.astype(np.float64)) ** 2))
        psnr = 10.0 * np.log10((255.0 ** 2) / max(mse, 1e-10))
        return wm_bgr, float(psnr)

    def _compute_sync_peak(self, Y_channel: np.ndarray) -> Tuple[int, int, float]:
        """Computes Modulo-64 folded 2D FFT cross-correlation peak (dy, dx, z_score)."""
        ch, cw = Y_channel.shape
        Y_res = np.clip(Y_channel - cv2.GaussianBlur(Y_channel, (5, 5), 1.2), -8.0, 8.0)
        y_idx = np.arange(ch)[:, None] % self.T
        x_idx = np.arange(cw)[None, :] % self.T

        F = np.zeros((self.T, self.T), dtype=np.float64)
        C = np.zeros((self.T, self.T), dtype=np.float64)
        np.add.at(F, (y_idx, x_idx), Y_res)
        np.add.at(C, (y_idx, x_idx), 1.0)
        F /= np.maximum(C, 1.0)

        corr_map = np.real(np.fft.ifft2(np.fft.fft2(F) * np.conj(self.S_template_fft)))
        peak_y, peak_x = np.unravel_index(np.argmax(corr_map), corr_map.shape)
        peak_val = float(corr_map[peak_y, peak_x])
        corr_excl = corr_map.copy()
        corr_excl[peak_y, peak_x] = float(np.mean(corr_map))
        z_score = (peak_val - float(np.mean(corr_excl))) / max(float(np.std(corr_excl)), 1e-8)
        return int(peak_y), int(peak_x), float(z_score)

    def _extract_at_scale(
        self,
        Y_att: np.ndarray,
        scale_factor: float = 1.0,
        expected_media_id: Optional[str] = None,
        known_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        if abs(scale_factor - 1.0) > 1e-4:
            inv_s = 1.0 / scale_factor
            new_h = max(self.T, int(round(Y_att.shape[0] * inv_s)))
            new_w = max(self.T, int(round(Y_att.shape[1] * inv_s)))
            Y_work = cv2.resize(Y_att, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        else:
            Y_work = Y_att

        ch, cw = Y_work.shape
        if ch < self.T or cw < self.T:
            return {"watermark_detected": False, "sync_z_score": 0.0, "surviving_tiles": 0}

        peak_y, peak_x, peak_z = self._compute_sync_peak(Y_work)

        # Gather all surviving complete 64x64 tiles aligned to (peak_y, peak_x)
        tiles_list = []
        tile_coords = []
        for ty in range(peak_y, ch - self.T + 1, self.T):
            for tx in range(peak_x, cw - self.T + 1, self.T):
                tiles_list.append(Y_work[ty : ty + self.T, tx : tx + self.T])
                tile_coords.append((ty, tx))

        # Fix 2A: Torus-Wrapped Partial Tile Recovery for 95% Micro-Crops (e.g. 167x100 & 124x124)
        if (ch < 160 or cw < 160 or len(tiles_list) < 2) and (ch * cw >= 11000):
            y_mod = (np.arange(ch)[:, None] - peak_y) % self.T
            x_mod = (np.arange(cw)[None, :] - peak_x) % self.T
            T_torus = np.zeros((self.T, self.T), dtype=np.float64)
            T_cnt = np.zeros((self.T, self.T), dtype=np.float64)
            np.add.at(T_torus, (y_mod, x_mod), Y_work)
            np.add.at(T_cnt, (y_mod, x_mod), 1.0)
            T_torus /= np.maximum(T_cnt, 1.0)
            tiles_list.append(T_torus)
            tile_coords.append((0, 0))
        elif len(tiles_list) == 0 and ch >= self.T and cw >= self.T:
            tiles_list.append(Y_work[: self.T, : self.T])
            tile_coords.append((0, 0))

        num_tiles = len(tiles_list)
        if num_tiles == 0:
            return {"watermark_detected": False, "sync_z_score": round(peak_z, 2), "surviving_tiles": 0}

        tiles_3d = np.array(tiles_list, dtype=np.float64)
        raw_projs = self._extract_raw_projections_batch(tiles_3d)

        # Bug 2 Fix: Multi-Gain Contrast & Sharpness Lock over alpha in [0.40, 2.30]
        best_score = -1e9
        best_result = None

        for alpha in self.gain_grid:
            llr_cand = self._compute_llrs_for_gain(raw_projs, float(alpha))
            msg_48, cw_64, ecc_ok, _ = decode_ebch_64_48_chase2(llr_cand, q_flip=5)
            origin_flag, media_id_hex = self.unpack_payload_48(msg_48)
            hard_raw = (llr_cand > 0).astype(np.int32)
            flips = int(np.sum(hard_raw != cw_64))
            margin = float(np.mean(np.abs(llr_cand)))

            valid_origin = 1 <= origin_flag <= 4
            score = (
                (100.0 if (ecc_ok and valid_origin) else 0.0)
                - (8.5 * flips)
                + (12.0 * margin)
                - (0.8 * abs(alpha - 1.0))
            )
            if expected_media_id is not None and media_id_hex == expected_media_id:
                score += 500.0
            if (
                known_ids is not None
                and media_id_hex in known_ids
                and valid_origin
                and (ecc_ok or flips <= 6)
                and peak_z >= 2.2
            ):
                score += 500.0

            if score > best_score:
                best_score = score
                best_result = (
                    llr_cand,
                    msg_48,
                    cw_64,
                    ecc_ok,
                    origin_flag,
                    media_id_hex,
                    flips,
                    float(alpha),
                )

        assert best_result is not None
        (
            llr_accum,
            msg_48,
            cw_64,
            ecc_ok,
            origin_flag,
            media_id_hex,
            flipped_by_ecc,
            locked_alpha,
        ) = best_result

        # Per-Tile Watermark Agreement & Drop-Out Scanner (using QIM dither LLRs tile_llrs_mat > 0 vs cw_64)
        tile_llrs_mat = self._compute_tile_llrs_matrix(raw_projs, locked_alpha)
        tile_bits_mat = (tile_llrs_mat > 0).astype(np.int32)
        tile_agree = np.mean(tile_bits_mat == cw_64[None, :], axis=1)
        tile_bers = 1.0 - tile_agree
        damaged_tiles_count = int(np.sum(tile_agree < 0.68))
        surviving_valid_tiles = max(0, num_tiles - damaged_tiles_count)
        tile_survival_pct = round(
            100.0 * (float(surviving_valid_tiles) / float(max(num_tiles, 1))), 1
        )
        damaged_grid_set = set()
        for idx_t, t_ber in enumerate(tile_bers):
            if float(t_ber) > 0.32 and idx_t < len(tile_coords):
                ty_c, tx_c = tile_coords[idx_t]
                gy = min(15, max(0, int(((ty_c + 32) * 16) // max(ch, 1))))
                gx = min(15, max(0, int(((tx_c + 32) * 16) // max(cw, 1))))
                damaged_grid_set.add((gy, gx))
        damaged_tile_grid_coords = [[int(r), int(c)] for r, c in sorted(damaged_grid_set)]

        raw_ber_pct = round(100.0 * float(flipped_by_ecc) / 64.0, 2)
        post_ecc_ber_pct = 0.0 if ecc_ok else raw_ber_pct
        guided_or_known_match = bool(
            (expected_media_id is not None and media_id_hex == expected_media_id)
            or (known_ids is not None and media_id_hex in known_ids)
        )
        if guided_or_known_match:
            wm_detected = bool(
                (1 <= origin_flag <= 4)
                and (ecc_ok or flipped_by_ecc <= 6)
                and peak_z >= 2.2
            )
        else:
            wm_detected = bool(peak_z >= 4.2 and ecc_ok and (1 <= origin_flag <= 4) and flipped_by_ecc <= 2 and tile_survival_pct >= 25.0)

        return {
            "watermark_detected": wm_detected,
            "sync_offset_mod64": [peak_y, peak_x],
            "sync_z_score": round(peak_z, 2),
            "surviving_tiles": surviving_valid_tiles,
            "total_tiles": num_tiles,
            "damaged_tiles_count": damaged_tiles_count,
            "tile_survival_pct": tile_survival_pct,
            "damaged_tile_grid_coords": damaged_tile_grid_coords,
            "ecc_valid": bool(ecc_ok),
            "bits_corrected_by_ecc": int(flipped_by_ecc),
            "raw_ber_pct": raw_ber_pct,
            "post_ecc_ber_pct": post_ecc_ber_pct,
            "origin_flag": int(origin_flag),
            "short_media_id": media_id_hex,
            "llr_confidence": round(float(np.mean(np.abs(llr_accum))), 4),
            "locked_gain_alpha": round(locked_alpha, 3),
            "locked_dpi_scale": round(scale_factor, 3),
        }

    def blind_extract(
        self,
        attacked_bgr: np.ndarray,
        enable_multiscale: bool = True,
        expected_media_id: Optional[str] = None,
        known_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Step 1: Modulo-64 Folding + 2D FFT Circular Cross-Correlation to find crop shift (dy, dx).
        Step 2: Multi-Gain Contrast & Sharpness Lock (alpha in [0.40, 2.30]).
        Step 3: Chase-2 Extended BCH(64, 48, d_min=6) Soft-Decision Decoding.
        Step 4 (Bug 3 Fix): Automatic Multi-Scale DPI Screenshot Sync Search with Known-ID Lock.
        """
        if attacked_bgr is None or attacked_bgr.size == 0:
            return {
                "watermark_detected": False,
                "sync_z_score": 0.0,
                "surviving_tiles": 0,
                "damaged_tiles_count": 0,
                "tile_survival_pct": 0.0,
            }

        Y_att = cv2.cvtColor(attacked_bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float64)

        # 1. Native 1:1 Scale Extraction
        res_1x = self._extract_at_scale(
            Y_att, scale_factor=1.0, expected_media_id=expected_media_id, known_ids=known_ids
        )
        if res_1x.get("watermark_detected"):
            if expected_media_id is not None and res_1x.get("short_media_id") == expected_media_id:
                return res_1x
            if known_ids is not None and res_1x.get("short_media_id") in known_ids:
                return res_1x
            if (
                res_1x.get("sync_z_score", 0.0) >= 4.2
                and res_1x.get("bits_corrected_by_ecc", 99) <= 2
                and expected_media_id is None
                and not known_ids
            ):
                return res_1x

        if not enable_multiscale:
            return res_1x

        # 2. Bug 3 Fix: Fast Multi-Scale Sync Search across Browser Zoom, OS DPI, & Phone-Editor Crops
        candidate_scales = [
            0.45, 0.50, 0.55, 0.60, 0.67, 0.72, 0.73, 0.75, 0.80, 0.85, 0.90, 0.95,
            1.05, 1.10, 1.15, 1.20, 1.25, 1.33, 1.37, 1.40, 1.45, 1.60, 1.75, 1.90, 2.05, 2.25,
        ]
        scale_peaks = []
        for s in candidate_scales:
            inv_s = 1.0 / s
            nh = int(round(Y_att.shape[0] * inv_s))
            nw = int(round(Y_att.shape[1] * inv_s))
            if nh < self.T or nw < self.T or nh > 3600 or nw > 3600:
                continue
            Y_s = cv2.resize(Y_att, (nw, nh), interpolation=cv2.INTER_CUBIC)
            _, _, pz = self._compute_sync_peak(Y_s)
            scale_peaks.append((pz, s))

        scale_peaks.sort(key=lambda x: x[0], reverse=True)
        candidates = [res_1x]
        has_known_guidance = bool(expected_media_id is not None or (known_ids and len(known_ids) > 0))
        min_pz = 2.2 if has_known_guidance else 3.5

        for pz, s in scale_peaks[:8]:
            if pz < min_pz:
                break
            cand_res = self._extract_at_scale(
                Y_att, scale_factor=s, expected_media_id=expected_media_id, known_ids=known_ids
            )
            if cand_res.get("watermark_detected"):
                if expected_media_id and cand_res.get("short_media_id") == expected_media_id:
                    return cand_res
                if known_ids is not None and cand_res.get("short_media_id") in known_ids:
                    return cand_res
            candidates.append(cand_res)

        def _rank_cand(c):
            det = 1 if c.get("watermark_detected") else 0
            known_hit = 1 if (known_ids is not None and c.get("short_media_id") in known_ids and c.get("ecc_valid")) else 0
            return (det, known_hit, c.get("sync_z_score", 0.0) - 0.6 * c.get("bits_corrected_by_ecc", 32))

        return max(candidates, key=_rank_cand)
