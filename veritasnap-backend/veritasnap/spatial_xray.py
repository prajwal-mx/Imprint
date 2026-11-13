from typing import Tuple, Dict, Any, Optional, List
import numpy as np
import cv2
from .watermark_engine import (
    compute_canonical_dimensions,
    orient_image_dihedral,
    DIHEDRAL_LABELS,
)


def compute_phash_64(img_bgr: np.ndarray) -> int:
    """Computes a 64-bit DCT perceptual hash for fast candidate pre-filtering."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct_mat = cv2.dct(resized)
    low_freq = dct_mat[:8, :8].flatten()
    med = float(np.median(low_freq[1:]))
    bits = (low_freq > med).astype(np.uint64)
    val = 0
    for i, b in enumerate(bits):
        if b:
            val |= 1 << int(i)
    return int(val & ((1 << 63) - 1))


class SpatialTamperXRayScanner:
    """
    Path B (SIFT + USAC_MAGSAC) + Path C (Multi-Scale Low-Pass Structural Pyramid Lock)
    + 8-Way Dihedral Orientation & Mirror Scanner (D_4 Symmetry Group)
    + 16x16 Shift-Tolerant YCrCb Spatial Integrity Scanner with 3-Channel B&W Calibration.
    """

    def __init__(self, max_canonical_dim: int = 1408, grid_n: int = 16):
        self.max_canonical_dim = max_canonical_dim
        self.grid_n = grid_n
        self.sift = cv2.SIFT_create(
            nfeatures=2500,
            nOctaveLayers=4,
            contrastThreshold=0.02,
            edgeThreshold=14,
            sigma=1.6,
        )

    def get_canonical_size(self, img_bgr: np.ndarray) -> Tuple[int, int]:
        h, w = img_bgr.shape[:2]
        return compute_canonical_dimensions(h, w, max_dim=self.max_canonical_dim, tile_size=64)

    @staticmethod
    def _normalized_gaussian_blur(
        img_bgr: np.ndarray, valid_mask_u8: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Boundary-Normalized Convolution (G * (I * M)) / (G * M)
        so black un-warped borders outside a cropped screenshot NEVER bleed into interior cells.
        """
        img_f = img_bgr.astype(np.float64)
        if valid_mask_u8 is None:
            return cv2.GaussianBlur(img_f, (15, 15), 3.0)

        m_f = (valid_mask_u8 > 127).astype(np.float64)[:, :, None]
        num = cv2.GaussianBlur(img_f * m_f, (15, 15), 3.0)
        den = cv2.GaussianBlur(m_f, (15, 15), 3.0)
        if den.ndim == 2:
            den = den[:, :, None]
        return np.where(den > 1e-4, num / np.maximum(den, 1e-4), img_f)

    def compute_canonical_signature(
        self,
        img_bgr: np.ndarray,
        canonical_w: int,
        canonical_h: int,
        valid_mask_u8: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Computes 16x16x18 shift-tolerant low-frequency YCrCb signature
        in the exact (canonical_w, canonical_h) frame.
        """
        if img_bgr.shape[1] != canonical_w or img_bgr.shape[0] != canonical_h:
            img_res = cv2.resize(
                img_bgr, (canonical_w, canonical_h), interpolation=cv2.INTER_AREA
            )
        else:
            img_res = img_bgr

        img_smooth = self._normalized_gaussian_blur(img_res, valid_mask_u8)
        img_smooth_u8 = np.clip(np.round(img_smooth), 0, 255).astype(np.uint8)
        ycrcb = cv2.cvtColor(img_smooth_u8, cv2.COLOR_BGR2YCrCb).astype(np.float64)
        Y, Cr, Cb = ycrcb[:, :, 0], ycrcb[:, :, 1], ycrcb[:, :, 2]

        cell_h = canonical_h // self.grid_n
        cell_w = canonical_w // self.grid_n
        sigs = np.zeros((self.grid_n, self.grid_n, 18), dtype=np.float32)

        for gy in range(self.grid_n):
            y0, y1 = gy * cell_h, (gy + 1) * cell_h
            for gx in range(self.grid_n):
                x0, x1 = gx * cell_w, (gx + 1) * cell_w
                if valid_mask_u8 is not None:
                    m_cell = valid_mask_u8[y0:y1, x0:x1] > 127
                    if np.any(m_cell):
                        y_cell = Y[y0:y1, x0:x1]
                        c_mean_y = float(np.mean(y_cell[m_cell]))
                        sub_h = max(1, (y1 - y0) // 4)
                        sub_w = max(1, (x1 - x0) // 4)
                        sub_vals = np.empty(16, dtype=np.float32)
                        idx = 0
                        for sy in range(4):
                            sy0 = sy * sub_h
                            sy1 = (y1 - y0) if sy == 3 else (sy + 1) * sub_h
                            for sx in range(4):
                                sx0 = sx * sub_w
                                sx1 = (x1 - x0) if sx == 3 else (sx + 1) * sub_w
                                m_sub = m_cell[sy0:sy1, sx0:sx1]
                                if np.any(m_sub):
                                    sub_vals[idx] = float(np.mean(y_cell[sy0:sy1, sx0:sx1][m_sub]))
                                else:
                                    sub_vals[idx] = c_mean_y
                                idx += 1
                        sigs[gy, gx, :16] = sub_vals
                        sigs[gy, gx, 16] = float(np.mean(Cr[y0:y1, x0:x1][m_cell]))
                        sigs[gy, gx, 17] = float(np.mean(Cb[y0:y1, x0:x1][m_cell]))
                        continue
                py = cv2.resize(Y[y0:y1, x0:x1], (4, 4), interpolation=cv2.INTER_AREA)
                pcr = Cr[y0:y1, x0:x1]
                pcb = Cb[y0:y1, x0:x1]
                sigs[gy, gx, :16] = py.flatten().astype(np.float32)
                sigs[gy, gx, 16] = float(np.mean(pcr))
                sigs[gy, gx, 17] = float(np.mean(pcb))
        return sigs

    def _detect_keypoints_safe(
        self, img_bgr: np.ndarray
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Runs SIFT on an 800px Gaussian-smoothed copy AND a CLAHE-enhanced copy
        so LCD monitor Moiré grids and extreme S-curve Black & White filters
        always yield strong, scale-invariant keypoints.
        """
        h, w = img_bgr.shape[:2]
        gray_full = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        work_scale = min(1.0, 800.0 / float(max(h, w, 1)))
        if work_scale < 1.0:
            gw = max(64, int(round(w * work_scale)))
            gh = max(64, int(round(h * work_scale)))
            gray = cv2.resize(gray_full, (gw, gh), interpolation=cv2.INTER_AREA)
        else:
            gray = gray_full
        gray_smooth = cv2.GaussianBlur(gray, (5, 5), 1.4)

        kp1, des1 = self.sift.detectAndCompute(gray_smooth, None)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        kp2, des2 = self.sift.detectAndCompute(clahe.apply(gray_smooth), None)

        inv_scale_x = float(w) / float(gray.shape[1])
        inv_scale_y = float(h) / float(gray.shape[0])

        pts_list = []
        des_list = []
        if kp1 and des1 is not None and len(kp1) > 0:
            pts1 = np.float32([[k.pt[0] * inv_scale_x, k.pt[1] * inv_scale_y] for k in kp1])
            pts_list.append(pts1)
            des_list.append(des1.astype(np.float32))
        if kp2 and des2 is not None and len(kp2) > 0 and (des1 is None or len(kp1) < 180):
            pts2 = np.float32([[k.pt[0] * inv_scale_x, k.pt[1] * inv_scale_y] for k in kp2])
            pts_list.append(pts2)
            des_list.append(des2.astype(np.float32))

        if not pts_list:
            return np.zeros((0, 2), dtype=np.float32), None

        pts_all = np.vstack(pts_list)
        des_all = np.vstack(des_list)
        if len(pts_all) > 3000:
            pts_all = pts_all[:3000]
            des_all = des_all[:3000]
        return pts_all, des_all

    def extract_reference_features(
        self, img_bgr: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, int]:
        """
        Resizes input to aspect-preserving (W_can, H_can), extracts SIFT features
        and 16x16x18 Canonical Spatial Integrity Grid.
        Returns (img_can, pts, des, sigs, W_can, H_can).
        """
        w_can, h_can = self.get_canonical_size(img_bgr)
        interp = cv2.INTER_CUBIC if (w_can > img_bgr.shape[1] or h_can > img_bgr.shape[0]) else cv2.INTER_AREA
        img_can = cv2.resize(img_bgr, (w_can, h_can), interpolation=interp)
        pts, des = self._detect_keypoints_safe(img_can)
        if des is None:
            des = np.zeros((0, 128), dtype=np.float32)
        sigs = self.compute_canonical_signature(img_can, w_can, h_can)
        return img_can, pts, des, sigs, w_can, h_can

    def find_best_dihedral_orientation(
        self,
        query_bgr: np.ndarray,
        ref_can_bgr: Optional[np.ndarray],
    ) -> Tuple[np.ndarray, int, float]:
        """
        8-Way Dihedral Orientation & Mirror Scanner (D_4 Group: 0°, 90°, 180°, 270° x Normal/Mirrored).
        Matches Sobel Edge Magnitude (|∇Y|) + High-Pass Luminance across all 8 dihedral symmetries
        in ~0.8 ms so rotated and horizontally/vertically mirrored images snap upright automatically!
        """
        if ref_can_bgr is None or ref_can_bgr.size == 0 or query_bgr is None or query_bgr.size == 0:
            return query_bgr, 0, 0.0

        sz = 160
        ref_sq = cv2.resize(ref_can_bgr, (sz, sz), interpolation=cv2.INTER_AREA)
        ref_g = cv2.GaussianBlur(cv2.cvtColor(ref_sq, cv2.COLOR_BGR2GRAY), (5, 5), 1.4).astype(np.float32)
        ref_y = ref_g - 0.70 * cv2.GaussianBlur(ref_g, (25, 25), 6.0)
        ref_gx = cv2.Sobel(ref_g, cv2.CV_32F, 1, 0, ksize=3)
        ref_gy = cv2.Sobel(ref_g, cv2.CV_32F, 0, 1, ksize=3)
        ref_edge = np.sqrt(ref_gx ** 2 + ref_gy ** 2)

        q_sq_0 = cv2.resize(query_bgr, (sz, sz), interpolation=cv2.INTER_AREA)
        q_g_0 = cv2.GaussianBlur(cv2.cvtColor(q_sq_0, cv2.COLOR_BGR2GRAY), (5, 5), 1.4).astype(np.float32)

        scores = []
        for code in range(8):
            q_g = orient_image_dihedral(q_g_0, code)
            q_y = q_g - 0.70 * cv2.GaussianBlur(q_g, (25, 25), 6.0)
            q_gx = cv2.Sobel(q_g, cv2.CV_32F, 1, 0, ksize=3)
            q_gy = cv2.Sobel(q_g, cv2.CV_32F, 0, 1, ksize=3)
            q_edge = np.sqrt(q_gx ** 2 + q_gy ** 2)

            ce_full = float(cv2.matchTemplate(ref_edge, q_edge, cv2.TM_CCOEFF_NORMED)[0, 0])
            cy_full = abs(float(cv2.matchTemplate(ref_y, q_y, cv2.TM_CCOEFF_NORMED)[0, 0]))
            _, ce_crop, _, _ = cv2.minMaxLoc(
                cv2.matchTemplate(ref_edge, q_edge[20:140, 20:140], cv2.TM_CCOEFF_NORMED)
            )
            sc = max(0.75 * ce_full + 0.25 * cy_full, 0.88 * float(ce_crop))
            scores.append((sc, code))

        score_0 = scores[0][0]
        best_sc, best_code = max(scores, key=lambda x: x[0])
        if best_code != 0 and best_sc >= 0.42 and best_sc > score_0 + 0.08:
            return orient_image_dihedral(query_bgr, best_code), best_code, round(best_sc, 3)
        return query_bgr, 0, round(score_0, 3)

    def _match_subpatch_microcrop_fallback(
        self,
        query_bgr: np.ndarray,
        ref_can_bgr: Optional[np.ndarray],
        canonical_w: int,
        canonical_h: int,
    ) -> Tuple[Optional[np.ndarray], float]:
        """
        Fix 2B: Direct Sub-Patch Template Sliding for 95% Micro-Crops (e.g., 167x100 & 124x124 sky/treetops).
        Slides query_bgr over ref_can_bgr across scales [0.75, 0.90, 1.0, 1.15, 1.30] matching both
        3-channel BGR color (corr_bgr) and high-pass Laplacian/gradient detail (corr_hp).
        """
        if ref_can_bgr is None or ref_can_bgr.size == 0 or query_bgr is None or query_bgr.size == 0:
            return None, 0.0
        qh, qw = query_bgr.shape[:2]
        if (qh * qw) < 11000 or float(np.std(query_bgr)) < 1.5:
            return None, 0.0
        if max(qh, qw) >= 360 and (qh * qw) >= int(0.28 * canonical_w * canonical_h):
            return None, 0.0

        ref_blur = cv2.GaussianBlur(ref_can_bgr, (5, 5), 1.2).astype(np.float32)
        ref_gray = cv2.cvtColor(ref_can_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        ref_hp = cv2.GaussianBlur(ref_gray, (3, 3), 0.8) - cv2.GaussianBlur(ref_gray, (19, 19), 5.0)

        best_corr = -1.0
        best_H = None

        for s in [0.75, 0.90, 1.0, 1.15, 1.30]:
            tw = int(round(qw * s))
            th = int(round(qh * s))
            if tw < 32 or th < 32 or tw >= canonical_w or th >= canonical_h:
                continue
            q_res = cv2.resize(query_bgr, (tw, th), interpolation=cv2.INTER_AREA)
            q_blur = cv2.GaussianBlur(q_res, (5, 5), 1.2).astype(np.float32)
            q_gray = cv2.cvtColor(q_res, cv2.COLOR_BGR2GRAY).astype(np.float32)
            q_hp = cv2.GaussianBlur(q_gray, (3, 3), 0.8) - cv2.GaussianBlur(q_gray, (19, 19), 5.0)

            res_bgr = cv2.matchTemplate(ref_blur, q_blur, cv2.TM_CCOEFF_NORMED)
            _, max_bgr, _, loc_bgr = cv2.minMaxLoc(res_bgr)

            res_hp = cv2.matchTemplate(ref_hp, q_hp, cv2.TM_CCOEFF_NORMED)
            _, max_hp, _, loc_hp = cv2.minMaxLoc(res_hp)

            for c_val, loc in [(float(max_hp), loc_hp), (float(max_bgr), loc_bgr)]:
                mx, my = loc
                ref_patch = ref_blur[my : my + th, mx : mx + tw]
                mean_rgb_diff = float(np.mean(np.abs(ref_patch - q_blur))) / 255.0
                if c_val >= 0.42 and mean_rgb_diff < (18.0 / 255.0) and c_val > best_corr:
                    best_corr = c_val
                    sx = float(tw) / float(max(qw, 1))
                    sy = float(th) / float(max(qh, 1))
                    best_H = np.array([[sx, 0.0, float(mx)], [0.0, sy, float(my)], [0.0, 0.0, 1.0]], dtype=np.float64)

        if best_H is not None and best_corr >= 0.42:
            return best_H, round(best_corr, 3)
        return None, 0.0

    def _match_structural_pyramid_fallback(
        self,
        query_bgr: np.ndarray,
        ref_can_bgr: Optional[np.ndarray],
        canonical_w: int,
        canonical_h: int,
    ) -> Tuple[Optional[np.ndarray], np.ndarray, float, int]:
        """
        Aspect-Ratio-Preserving, B&W-Safe, 8-Way Dihedral & Multi-Scale Structural Matcher:
          1. Small 2-to-6 cell crops (preserving the crop's true aspect ratio qw/qh across scales 0.20..0.95)
          2. Black & White / Solarize / Artistic filters (CLAHE luminance + Sobel edges, zero raw RGB color rejection)
          3. AI-Regenerated (Diffusion img2img) & AI-Outpainted images (reverse template scales 0.35..0.92)
          4. All 8 Dihedral Orientations (0/90/180/270 deg rotations x Normal/Mirrored)
        Returns (H_mat, oriented_query_bgr, best_corr, best_orient_code).
        """
        if ref_can_bgr is None or ref_can_bgr.size == 0 or query_bgr is None or query_bgr.size == 0:
            return None, query_bgr, 0.0, 0

        work_w = 256
        work_h = max(144, int(round(256.0 * canonical_h / max(canonical_w, 1))))
        ref_small = cv2.resize(ref_can_bgr, (work_w, work_h), interpolation=cv2.INTER_AREA)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        ref_gray = cv2.cvtColor(ref_small, cv2.COLOR_BGR2GRAY)
        ref_y = cv2.GaussianBlur(clahe.apply(ref_gray), (5, 5), 1.4).astype(np.float32)
        ref_gx = cv2.Sobel(ref_y, cv2.CV_32F, 1, 0, ksize=3)
        ref_gy = cv2.Sobel(ref_y, cv2.CV_32F, 0, 1, ksize=3)
        ref_edge = cv2.GaussianBlur(np.sqrt(ref_gx ** 2 + ref_gy ** 2), (5, 5), 1.2)

        best_corr = -1.0
        best_H = None
        best_query = query_bgr
        best_code = 0

        for code in range(8):
            q_orient = orient_image_dihedral(query_bgr, code)
            qh, qw = q_orient.shape[:2]
            q_aspect = float(qw) / float(max(qh, 1))

            q_gray_full = cv2.cvtColor(q_orient, cv2.COLOR_BGR2GRAY)
            q_clahe_full = cv2.GaussianBlur(clahe.apply(q_gray_full), (5, 5), 1.4).astype(np.float32)

            # A. Test exact full-frame match (tw = work_w, th = work_h) + scaled full-aspect boxes
            candidate_boxes = [(work_w, work_h, True)]
            for s_full in [0.90, 0.80, 0.70]:
                candidate_boxes.append((int(round(work_w * s_full)), int(round(work_h * s_full)), True))

            # B. Add aspect-ratio-preserving sub-crop sizes from 20% up to 95% of reference width (for 2-to-6 cell crops)
            for w_frac in [0.20, 0.24, 0.28, 0.33, 0.38, 0.45, 0.55, 0.68, 0.82, 0.95]:
                tw = int(round(work_w * w_frac))
                th = int(round(tw / max(q_aspect, 0.1)))
                if 18 <= tw <= work_w and 18 <= th <= work_h:
                    candidate_boxes.append((tw, th, False))

            for (tw, th, is_full_aspect) in candidate_boxes:
                q_y = cv2.resize(q_clahe_full, (tw, th), interpolation=cv2.INTER_AREA)
                q_gx = cv2.Sobel(q_y, cv2.CV_32F, 1, 0, ksize=3)
                q_gy = cv2.Sobel(q_y, cv2.CV_32F, 0, 1, ksize=3)
                q_edge = cv2.GaussianBlur(np.sqrt(q_gx ** 2 + q_gy ** 2), (5, 5), 1.2)

                res_y = cv2.matchTemplate(ref_y, q_y, cv2.TM_CCOEFF_NORMED)
                min_y, max_y, _, max_loc_y = cv2.minMaxLoc(res_y)

                res_e = cv2.matchTemplate(ref_edge, q_edge, cv2.TM_CCOEFF_NORMED)
                _, max_e, _, max_loc_e = cv2.minMaxLoc(res_e)

                mx_y, my_y = max_loc_y
                mx_e, my_e = max_loc_e
                co_score_y = 0.55 * float(max_y) + 0.45 * float(res_e[my_y, mx_y])
                co_score_e = 0.55 * float(res_y[my_e, mx_e]) + 0.45 * float(max_e)
                lum_score = max(float(max_y), abs(float(min_y)) * 0.85)
                sol_score = (0.82 * float(max_e) + 0.18 * lum_score) if is_full_aspect else 0.0
                score = max(co_score_y, co_score_e, sol_score)

                if code != 0:
                    score -= 0.04
                if tw < work_w * 0.45:
                    score -= 0.04

                # Require >= 0.56 for small sub-crop boxes (< 65% width) so random patches on unrelated images never false-match
                min_req = 0.36 if (is_full_aspect and tw >= work_w * 0.75) else 0.56
                if score >= min_req and score > best_corr:
                    best_corr = score
                    mx, my = max_loc_y if co_score_y >= co_score_e else max_loc_e
                    sx = (tw / float(work_w)) * (float(canonical_w) / float(qw))
                    sy = (th / float(work_h)) * (float(canonical_h) / float(qh))
                    tx = (mx / float(work_w)) * float(canonical_w)
                    ty = (my / float(work_h)) * float(canonical_h)
                    best_H = np.array([[sx, 0.0, tx], [0.0, sy, ty], [0.0, 0.0, 1.0]], dtype=np.float64)
                    best_query = q_orient
                    best_code = code

            # C. Reverse template search for AI Outpainting / Expanded Borders on upright/flipped frames
            if code in (0, 2):
                q_base = cv2.resize(q_clahe_full, (work_w, work_h), interpolation=cv2.INTER_AREA)
                q_gx_b = cv2.Sobel(q_base, cv2.CV_32F, 1, 0, ksize=3)
                q_gy_b = cv2.Sobel(q_base, cv2.CV_32F, 0, 1, ksize=3)
                q_edge_b = cv2.GaussianBlur(np.sqrt(q_gx_b ** 2 + q_gy_b ** 2), (5, 5), 1.2)
                for inner_s in [0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.92]:
                    tw = max(48, int(round(work_w * inner_s)))
                    th = max(48, int(round(work_h * inner_s)))
                    if tw >= work_w or th >= work_h:
                        continue
                    Sub_ref = cv2.resize(ref_y, (tw, th), interpolation=cv2.INTER_AREA)
                    Sub_edge = cv2.resize(ref_edge, (tw, th), interpolation=cv2.INTER_AREA)
                    res_rev = cv2.matchTemplate(q_base, Sub_ref, cv2.TM_CCOEFF_NORMED)
                    _, max_val_r, _, max_loc_r = cv2.minMaxLoc(res_rev)
                    res_rev_e = cv2.matchTemplate(q_edge_b, Sub_edge, cv2.TM_CCOEFF_NORMED)
                    _, max_val_re, _, max_loc_re = cv2.minMaxLoc(res_rev_e)
                    mx_r, my_r = max_loc_r
                    mx_re, my_re = max_loc_re
                    comb_rev = max(
                        0.55 * float(max_val_r) + 0.45 * float(res_rev_e[my_r, mx_r]),
                        0.55 * float(res_rev[my_re, mx_re]) + 0.45 * float(max_val_re),
                    )
                    if code != 0:
                        comb_rev -= 0.04
                    if comb_rev >= 0.46 and comb_rev > best_corr:
                        best_corr = comb_rev
                        mx, my = max_loc_re if float(max_val_re) >= float(max_val_r) else max_loc_r
                        q_x0 = (mx / float(work_w)) * float(qw)
                        q_y0 = (my / float(work_h)) * float(qh)
                        q_w_box = (tw / float(work_w)) * float(qw)
                        q_h_box = (th / float(work_h)) * float(qh)
                        sx = float(canonical_w) / max(q_w_box, 1.0)
                        sy = float(canonical_h) / max(q_h_box, 1.0)
                        tx = -q_x0 * sx
                        ty = -q_y0 * sy
                        best_H = np.array([[sx, 0.0, tx], [0.0, sy, ty], [0.0, 0.0, 1.0]], dtype=np.float64)
                        best_query = q_orient
                        best_code = code

        if best_corr >= 0.36 and best_H is not None:
            return best_H, best_query, round(best_corr, 3), best_code
        return None, query_bgr, round(best_corr, 3), 0

    @staticmethod
    def _is_homography_well_conditioned(H_mat: Optional[np.ndarray]) -> bool:
        """
        Validates 3x3 homography matrix determinant, SVD condition number,
        and projective perspective terms (allowing reflections det != 0 as well).
        """
        if H_mat is None or H_mat.shape != (3, 3) or not np.all(np.isfinite(H_mat)):
            return False
        if abs(H_mat[2, 2]) < 1e-6:
            return False
        H_norm = H_mat / H_mat[2, 2]
        A = H_norm[:2, :2]
        det_a = abs(float(np.linalg.det(A)))
        if det_a < 1e-4 or det_a > 1e4:
            return False
        svd_vals = np.linalg.svd(A, compute_uv=False)
        if svd_vals[1] < 1e-5 or (svd_vals[0] / svd_vals[1]) > 50.0:
            return False
        if abs(H_norm[2, 0]) > 0.08 or abs(H_norm[2, 1]) > 0.08:
            return False
        return True

    def _compute_calibrated_direct_diff(
        self, ref_sigs: np.ndarray, att_sigs: np.ndarray
    ) -> float:
        ref_Y = ref_sigs[:, :, :16].flatten().astype(np.float64)
        att_Y = att_sigs[:, :, :16].flatten().astype(np.float64)
        ref_zm = ref_Y - np.mean(ref_Y)
        att_zm = att_Y - np.mean(att_Y)
        denom = float(np.linalg.norm(ref_zm) * np.linalg.norm(att_zm))
        corr = float(np.dot(ref_zm, att_zm) / denom) if denom > 1e-6 else 0.0
        struct_div = max(0.0, 1.0 - max(0.0, corr))
        c_diff = float(np.mean(np.abs(ref_sigs[:, :, 16:] - att_sigs[:, :, 16:]))) / 255.0
        return float(0.75 * struct_div + 0.25 * c_diff)

    def _unmatched_response(
        self,
        query_bgr: np.ndarray,
        ref_pts: np.ndarray,
        ref_sigs: np.ndarray,
        canonical_w: int,
        canonical_h: int,
        wm_decoded_for_this_ref: bool,
        wm_surviving_tiles: int,
        inliers: int = 0,
        inlier_ratio: float = 0.0,
        structural_corr: float = 0.0,
        wm_tile_survival_pct: float = 0.0,
    ) -> Dict[str, Any]:
        att_sigs_direct = self.compute_canonical_signature(
            query_bgr, canonical_w, canonical_h
        )
        cal_diff = self._compute_calibrated_direct_diff(ref_sigs, att_sigs_direct)
        total_can_tiles = max(1, (canonical_w // 64) * (canonical_h // 64))
        est_cov_pct = (
            round(min(100.0, 100.0 * float(wm_surviving_tiles) / float(total_can_tiles)), 1)
            if wm_decoded_for_this_ref and wm_surviving_tiles > 0
            else 0.0
        )
        # Fix 3: Never set is_transplant simply because len(ref_pts) >= 25!
        # Only flag transplant when watermark survival is high (>= 82%) yet >80% of scene structure mismatches.
        is_transplant = bool(
            wm_decoded_for_this_ref
            and wm_surviving_tiles >= 4
            and wm_tile_survival_pct >= 82.0
            and cal_diff > 0.42
        )
        return {
            "matched": False,
            "matched_via": "NONE",
            "inliers": inliers,
            "inlier_ratio": round(inlier_ratio, 3),
            "structural_corr": round(structural_corr, 3),
            "coverage_pct": est_cov_pct,
            "median_anomaly": round(float(cal_diff), 4),
            "max_z_mad": 0.0,
            "num_tampered_cells": 0,
            "tampered_coords": [],
            "transplant_forgery": is_transplant,
            "diffusion_regenerated": False,
            "grayscale_detected": False,
            "detected_orientation_code": 0,
            "detected_orientation_label": "0° Normal",
            "rectified_bgr": None,
            "rectified_cal_bgr": None,
            "coverage_mask": None,
        }

    def rectify_and_scan(
        self,
        query_bgr: np.ndarray,
        ref_pts: np.ndarray,
        ref_des: np.ndarray,
        ref_sigs: np.ndarray,
        canonical_w: int = 1408,
        canonical_h: int = 960,
        wm_decoded_for_this_ref: bool = False,
        wm_surviving_tiles: int = 0,
        ref_can_bgr: Optional[np.ndarray] = None,
        wm_tile_survival_pct: float = 100.0,
        wm_damaged_grid_coords: Optional[List[List[int]]] = None,
    ) -> Dict[str, Any]:
        # Step 0 (Fix 1): 8-Way Dihedral Orientation & Mirror Auto-Snap
        orient_code = 0
        if ref_can_bgr is not None and not wm_decoded_for_this_ref:
            query_bgr, orient_code, _ = self.find_best_dihedral_orientation(query_bgr, ref_can_bgr)

        hsv_q0 = cv2.cvtColor(query_bgr, cv2.COLOR_BGR2HSV)
        med_q0 = cv2.medianBlur(query_bgr, 19)
        diff_med0 = np.max(np.abs(query_bgr.astype(np.int16) - med_q0.astype(np.int16)), axis=2)
        thin_marker_mask = ((hsv_q0[:, :, 1] > 85) & (hsv_q0[:, :, 2] > 60) & (diff_med0 > 20)).astype(np.uint8) * 255
        has_colored_marker = bool(float(np.mean(thin_marker_mask > 0)) > 0.012)
        query_clean_bgr = (
            cv2.inpaint(query_bgr, cv2.dilate(thin_marker_mask, np.ones((3, 3), np.uint8)), 3, cv2.INPAINT_TELEA)
            if has_colored_marker
            else query_bgr
        )

        pts_q, des_q = self._detect_keypoints_safe(query_bgr)

        def _match_sift(pts_query, des_query):
            good_m = []
            if (
                des_query is not None
                and ref_des is not None
                and len(pts_query) >= 4
                and len(ref_pts) >= 4
                and len(des_query) >= 4
                and len(ref_des) >= 4
                and des_query.shape[1] == ref_des.shape[1]
            ):
                bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
                raw_matches = bf.knnMatch(des_query, ref_des, k=2)
                for pair in raw_matches:
                    if len(pair) == 2:
                        m, n = pair
                        if m.distance < 0.80 * n.distance:
                            good_m.append(m)
            if len(good_m) >= 8:
                src_p = np.float32([pts_query[m.queryIdx] for m in good_m]).reshape(-1, 1, 2)
                dst_p = np.float32([ref_pts[m.trainIdx] for m in good_m]).reshape(-1, 1, 2)
                reproj_t = max(8.0, 0.012 * float(max(canonical_w, canonical_h)))
                try:
                    Hc, mk = None, None
                    best_inl = 0
                    for thr in [3.0]:
                        Ht, mkt = cv2.findHomography(src_p, dst_p, cv2.USAC_MAGSAC, float(thr))
                        if Ht is not None and mkt is not None and self._is_homography_well_conditioned(Ht):
                            cnt_t = int(np.sum(mkt))
                            if cnt_t > best_inl:
                                Hc, mk, best_inl = Ht, mkt, cnt_t
                            if best_inl >= 20:
                                break
                except cv2.error:
                    Hc, mk = None, None
                if Hc is not None and mk is not None and self._is_homography_well_conditioned(Hc):
                    mf = mk.ravel() > 0
                    inl = int(np.sum(mf))
                    if inl >= 12:
                        Hn = Hc / Hc[2, 2]
                        idst = dst_p[mf].reshape(-1, 2)
                        iw = float(np.max(idst[:, 0]) - np.min(idst[:, 0]))
                        ih = float(np.max(idst[:, 1]) - np.min(idst[:, 1]))
                        return Hn, inl, float(inl / max(len(good_m), 1)), iw * ih
            return None, 0, 0.0, 0.0

        H_mat, inliers, inlier_ratio, inlier_bbox_area = _match_sift(pts_q, des_q)
        matched_via = "SIFT_RANSAC"
        structural_corr = 0.0
        marker_suppression_used = False

        # Fix 2: O(2) Mirror + Continuous Tilt/Rotation SIFT Support
        # Any combination of arbitrary-angle tilts (0..360 deg), 90/180/270 rotations, and mirror flips
        # is a proper rotation of either query_bgr or cv2.flip(query_bgr, 1)!
        if H_mat is None or inliers < 15:
            q_mirr = cv2.flip(query_bgr, 1)
            pts_m, des_m = self._detect_keypoints_safe(q_mirr)
            Hm_mirr, inl_mirr, ir_mirr, ib_mirr = _match_sift(pts_m, des_m)
            if Hm_mirr is not None and inl_mirr > inliers and inl_mirr >= 12:
                query_bgr = q_mirr
                H_mat, inliers, inlier_ratio, inlier_bbox_area = Hm_mirr, inl_mirr, ir_mirr, ib_mirr
                orient_code = 2 if orient_code == 0 else orient_code

        # Fix 2B: Direct Sub-Patch Template Sliding for 95% Micro-Crops (167x100 & 124x124 sky/treetops)
        if H_mat is None or inliers < 12:
            H_sub, corr_sub = self._match_subpatch_microcrop_fallback(
                query_bgr, ref_can_bgr, canonical_w, canonical_h
            )
            if H_sub is not None and corr_sub >= 0.42:
                H_mat = H_sub
                structural_corr = corr_sub
                inliers = int(round(corr_sub * 100))
                inlier_ratio = float(corr_sub)
                inlier_bbox_area = float(canonical_w * canonical_h)
                matched_via = "MICRO_CROP_TEMPLATE_LOCK"

        # Colored Marker Suppression Fallback (sees through red/yellow/colored marker scribbles on tilted crops)
        if (H_mat is None or inliers < 12) and max(query_bgr.shape[:2]) >= 300:
            hsv_q = cv2.cvtColor(query_bgr, cv2.COLOR_BGR2HSV)
            marker_mask = ((hsv_q[:, :, 1] > 85) & (hsv_q[:, :, 2] > 60)).astype(np.uint8) * 255
            if float(np.mean(marker_mask > 0)) > 0.015:
                m_dil = cv2.dilate(marker_mask, np.ones((3, 3), np.uint8))
                inp_bgr = cv2.inpaint(query_bgr, m_dil, 3, cv2.INPAINT_TELEA)
                med_q = cv2.medianBlur(query_bgr, 19)
                diff_med = np.max(np.abs(query_bgr.astype(np.int16) - med_q.astype(np.int16)), axis=2)
                thin_mask = ((hsv_q[:, :, 1] > 85) & (hsv_q[:, :, 2] > 60) & (diff_med > 20)).astype(np.uint8) * 255
                thin_inp = cv2.inpaint(query_bgr, cv2.dilate(thin_mask, np.ones((3, 3), np.uint8)), 3, cv2.INPAINT_TELEA)
                max_ch_bgr = cv2.cvtColor(np.max(query_bgr, axis=2), cv2.COLOR_GRAY2BGR)
                cands_marker = [(thin_inp, 1.0), (inp_bgr, 1.0), (max_ch_bgr, 1.0)]
                if min(query_bgr.shape[:2]) < 640:
                    cands_marker.append(
                        (cv2.resize(max_ch_bgr, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC), 2.0)
                    )
                    cands_marker.append(
                        (cv2.resize(inp_bgr, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC), 2.0)
                    )
                for c_img, c_scale in cands_marker:
                    pq_m, dq_m = self._detect_keypoints_safe(c_img)
                    if c_scale != 1.0 and len(pq_m) > 0:
                        pq_m = pq_m / float(c_scale)
                    Hm, inl_m, ir_m, ib_m = _match_sift(pq_m, dq_m)
                    # Also allow >= 10 inliers when upscaled low-res screenshot has strong inlier ratio >= 0.25
                    if Hm is None and len(pq_m) >= 4 and dq_m is not None and ref_des is not None and len(ref_des) >= 4:
                        bf_m = cv2.BFMatcher(cv2.NORM_L2)
                        gm_m = [m for m, n in bf_m.knnMatch(dq_m, ref_des, k=2) if m.distance < 0.80 * n.distance]
                        if len(gm_m) >= 10:
                            sp_m = np.float32([pq_m[m.queryIdx] for m in gm_m]).reshape(-1, 1, 2)
                            dp_m = np.float32([ref_pts[m.trainIdx] for m in gm_m]).reshape(-1, 1, 2)
                            try:
                                Hc_m, mk_m = cv2.findHomography(sp_m, dp_m, cv2.USAC_MAGSAC, 6.0)
                                if Hc_m is not None and mk_m is not None and self._is_homography_well_conditioned(Hc_m):
                                    mf_m = mk_m.ravel() > 0
                                    cnt_m = int(np.sum(mf_m))
                                    if cnt_m >= 10 and (cnt_m / float(len(gm_m))) >= 0.25:
                                        Hm = Hc_m / Hc_m[2, 2]
                                        inl_m = max(cnt_m, 12)
                                        ir_m = float(cnt_m / float(len(gm_m)))
                                        idst_m = dp_m[mf_m].reshape(-1, 2)
                                        ib_m = float(np.max(idst_m[:, 0]) - np.min(idst_m[:, 0])) * float(np.max(idst_m[:, 1]) - np.min(idst_m[:, 1]))
                            except cv2.error:
                                pass
                    if Hm is not None and inl_m > inliers:
                        H_mat, inliers, inlier_ratio, inlier_bbox_area = Hm, inl_m, ir_m, ib_m
                        matched_via = "SIFT_RANSAC"
                        marker_suppression_used = True



        # Path C Structural Pyramid Fallback for Diffusion (img2img), Solarized Filters, & Outpainting
        # Note: If watermark already decoded across >=82% of full-frame tiles at 1.0x scale, do not shrink via reverse template!
        if (H_mat is None or inliers < 12) and not (wm_decoded_for_this_ref and wm_tile_survival_pct >= 82.0):
            H_pyr, q_pyr, corr_pyr, code_pyr = self._match_structural_pyramid_fallback(
                query_bgr, ref_can_bgr, canonical_w, canonical_h
            )
            structural_corr = corr_pyr
            if H_pyr is not None and corr_pyr >= 0.36:
                H_mat = H_pyr
                query_bgr = q_pyr
                if code_pyr != 0:
                    orient_code = code_pyr
                inliers = int(round(corr_pyr * 100))
                inlier_ratio = float(corr_pyr)
                inlier_bbox_area = float(canonical_w * canonical_h)
                matched_via = "STRUCTURAL_PYRAMID_PATH_C"

        # Fix 3: If Path A watermark ALREADY decoded for this reference (e.g., heavily scribbled image(3).png
        # where giant black marker blocked SIFT), align directly to canonical frame so 16x16 X-Ray runs!
        if H_mat is None and wm_decoded_for_this_ref:
            qh, qw = query_bgr.shape[:2]
            H_mat = np.array(
                [
                    [float(canonical_w) / float(max(qw, 1)), 0.0, 0.0],
                    [0.0, float(canonical_h) / float(max(qh, 1)), 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
            matched_via = "WATERMARK_SYNC_GRID"
            inlier_bbox_area = float(canonical_w * canonical_h)

        if H_mat is None:
            return self._unmatched_response(
                query_bgr,
                ref_pts,
                ref_sigs,
                canonical_w,
                canonical_h,
                wm_decoded_for_this_ref,
                wm_surviving_tiles,
                inliers=inliers,
                inlier_ratio=inlier_ratio,
                structural_corr=structural_corr,
                wm_tile_survival_pct=wm_tile_survival_pct,
            )

        rectified = cv2.warpPerspective(
            query_bgr,
            H_mat,
            (canonical_w, canonical_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        ones_mask = np.full(query_bgr.shape[:2], 255, dtype=np.uint8)
        q_max_ch = np.max(query_bgr, axis=2)
        non_black_rows = np.where(np.percentile(q_max_ch, 95, axis=1) > 15)[0]
        non_black_cols = np.where(np.percentile(q_max_ch, 95, axis=0) > 15)[0]
        if len(non_black_rows) >= 16 and len(non_black_cols) >= 16:
            r0_nb, r1_nb = int(non_black_rows[0]), int(non_black_rows[-1]) + 1
            c0_nb, c1_nb = int(non_black_cols[0]), int(non_black_cols[-1]) + 1
            if r0_nb > 4 or r1_nb < query_bgr.shape[0] - 4 or c0_nb > 4 or c1_nb < query_bgr.shape[1] - 4:
                ones_mask[:r0_nb, :] = 0
                ones_mask[r1_nb:, :] = 0
                ones_mask[:, :c0_nb] = 0
                ones_mask[:, c1_nb:] = 0
        raw_cov_mask = cv2.warpPerspective(
            ones_mask,
            H_mat,
            (canonical_w, canonical_h),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        # Reject single-corner/logo coincidence on unwatermarked images where inliers cover <22% of visible area
        cov_area = float(np.sum(raw_cov_mask > 127))
        if (
            matched_via == "SIFT_RANSAC"
            and not wm_decoded_for_this_ref
            and not marker_suppression_used
            and cov_area > 0.30 * float(canonical_w * canonical_h)
            and (inlier_bbox_area / max(cov_area, 1.0)) < 0.22
        ):
            return self._unmatched_response(
                query_bgr,
                ref_pts,
                ref_sigs,
                canonical_w,
                canonical_h,
                wm_decoded_for_this_ref,
                wm_surviving_tiles,
                inliers=0,
                inlier_ratio=0.0,
                structural_corr=structural_corr,
                wm_tile_survival_pct=wm_tile_survival_pct,
            )

        # Erode cov_mask with a 35x35 kernel so laptop monitor bezels are excluded from valid_cells
        cov_mask = cv2.erode(raw_cov_mask, np.ones((35, 35), dtype=np.uint8))

        att_sigs = self.compute_canonical_signature(
            rectified, canonical_w, canonical_h, valid_mask_u8=raw_cov_mask
        )
        if ref_can_bgr is not None and ref_can_bgr.shape[:2] == (canonical_h, canonical_w) and float(np.mean(raw_cov_mask > 127)) < 0.96:
            ref_sigs = self.compute_canonical_signature(
                ref_can_bgr, canonical_w, canonical_h, valid_mask_u8=raw_cov_mask
            )

        cell_h = canonical_h // self.grid_n
        cell_w = canonical_w // self.grid_n
        valid_cells = np.zeros((self.grid_n, self.grid_n), dtype=bool)
        for gy in range(self.grid_n):
            y0, y1 = gy * cell_h, (gy + 1) * cell_h
            for gx in range(self.grid_n):
                x0, x1 = gx * cell_w, (gx + 1) * cell_w
                if np.mean(cov_mask[y0:y1, x0:x1] > 0) > 0.85:
                    valid_cells[gy, gx] = True

        if np.sum(valid_cells) < 4:
            for gy in range(self.grid_n):
                y0, y1 = gy * cell_h, (gy + 1) * cell_h
                for gx in range(self.grid_n):
                    x0, x1 = gx * cell_w, (gx + 1) * cell_w
                    if np.mean(raw_cov_mask[y0:y1, x0:x1] > 0) > 0.75:
                        valid_cells[gy, gx] = True

        if np.sum(valid_cells) < 2:
            for gy in range(self.grid_n):
                y0, y1 = gy * cell_h, (gy + 1) * cell_h
                for gx in range(self.grid_n):
                    x0, x1 = gx * cell_w, (gx + 1) * cell_w
                    if np.mean(raw_cov_mask[y0:y1, x0:x1] > 0) > 0.05:
                        valid_cells[gy, gx] = True

        if np.sum(valid_cells) < 2:
            return self._unmatched_response(
                query_bgr,
                ref_pts,
                ref_sigs,
                canonical_w,
                canonical_h,
                wm_decoded_for_this_ref,
                wm_surviving_tiles,
                inliers=0,
                inlier_ratio=0.0,
                structural_corr=structural_corr,
                wm_tile_survival_pct=wm_tile_survival_pct,
            )

        # Optional pixel-level smoothed YCrCb maps
        ref_smooth_ycrcb = None
        att_smooth_ycrcb = None
        if ref_can_bgr is not None and ref_can_bgr.shape[:2] == (canonical_h, canonical_w):
            ref_s_u8 = np.clip(np.round(self._normalized_gaussian_blur(ref_can_bgr)), 0, 255).astype(np.uint8)
            att_s_u8 = np.clip(np.round(self._normalized_gaussian_blur(rectified, raw_cov_mask)), 0, 255).astype(np.uint8)
            ref_smooth_ycrcb = cv2.cvtColor(ref_s_u8, cv2.COLOR_BGR2YCrCb).astype(np.float64)
            att_smooth_ycrcb = cv2.cvtColor(att_s_u8, cv2.COLOR_BGR2YCrCb).astype(np.float64)

        # Detect Grayscale / Online B&W Filter FIRST so 3-Channel B&W Calibration runs before correlation checks
        ref_Cr_vis = ref_sigs[valid_cells, 16].flatten().astype(np.float64)
        att_Cr_vis = att_sigs[valid_cells, 16].flatten().astype(np.float64)
        ref_Cb_vis = ref_sigs[valid_cells, 17].flatten().astype(np.float64)
        att_Cb_vis = att_sigs[valid_cells, 17].flatten().astype(np.float64)

        std_att_cr = float(np.std(att_Cr_vis))
        std_att_cb = float(np.std(att_Cb_vis))
        std_ref_chroma = max(float(np.std(ref_Cr_vis) + np.std(ref_Cb_vis)), 1.0)
        grayscale_detected = bool(
            (std_att_cr < 3.2 and std_att_cb < 3.2)
            or ((std_att_cr + std_att_cb) / std_ref_chroma < 0.18)
        )

        # Fix 2C: 3-Channel (Y, Cr, Cb) + Quadratic S-Curve Least-Squares Regression for Online B&W Filters
        ref_y_eff_grid = ref_sigs[:, :, :16].astype(np.float64).copy()
        bw_regression_active = False
        if grayscale_detected:
            # Build 4x4 sub-block Cr and Cb maps for each cell
            cr_sub_grid = np.repeat(ref_sigs[:, :, 16:17].astype(np.float64), 16, axis=2)
            cb_sub_grid = np.repeat(ref_sigs[:, :, 17:18].astype(np.float64), 16, axis=2)
            if ref_smooth_ycrcb is not None:
                for gy in range(self.grid_n):
                    y0, y1 = gy * cell_h, (gy + 1) * cell_h
                    for gx in range(self.grid_n):
                        x0, x1 = gx * cell_w, (gx + 1) * cell_w
                        cr_4x4 = cv2.resize(ref_smooth_ycrcb[y0:y1, x0:x1, 1], (4, 4), interpolation=cv2.INTER_AREA)
                        cb_4x4 = cv2.resize(ref_smooth_ycrcb[y0:y1, x0:x1, 2], (4, 4), interpolation=cv2.INTER_AREA)
                        cr_sub_grid[gy, gx, :] = cr_4x4.flatten()
                        cb_sub_grid[gy, gx, :] = cb_4x4.flatten()

            ry_flat = ref_y_eff_grid[valid_cells].flatten()
            rcr_flat = cr_sub_grid[valid_cells].flatten() - 128.0
            rcb_flat = cb_sub_grid[valid_cells].flatten() - 128.0
            ay_flat = att_sigs[valid_cells, :16].flatten().astype(np.float64)
            mask_fit = (ay_flat > 5.0) & (ay_flat < 250.0)
            if int(np.sum(mask_fit)) >= 32:
                X_bw = np.column_stack([
                    ry_flat[mask_fit],
                    rcr_flat[mask_fit],
                    rcb_flat[mask_fit],
                    ((ry_flat[mask_fit] - 128.0) ** 2) / 128.0,
                    np.ones_like(ry_flat[mask_fit]),
                ])
                try:
                    beta, _, _, _ = np.linalg.lstsq(X_bw, ay_flat[mask_fit], rcond=None)
                    if 0.15 <= beta[0] <= 2.8 and abs(beta[1]) <= 2.4 and abs(beta[2]) <= 2.4 and abs(beta[3]) <= 1.5:
                        for gy in range(self.grid_n):
                            for gx in range(self.grid_n):
                                ry_c = ref_y_eff_grid[gy, gx, :]
                                rcr_c = cr_sub_grid[gy, gx, :] - 128.0
                                rcb_c = cb_sub_grid[gy, gx, :] - 128.0
                                pred_c = (
                                    beta[0] * ry_c
                                    + beta[1] * rcr_c
                                    + beta[2] * rcb_c
                                    + beta[3] * (((ry_c - 128.0) ** 2) / 128.0)
                                    + beta[4]
                                )
                                ref_y_eff_grid[gy, gx, :] = np.clip(pred_c, 0.0, 255.0)
                        bw_regression_active = True
                except np.linalg.LinAlgError:
                    pass

        # 1. Global & Local Structural Correlation Check
        ref_Y_vis = ref_y_eff_grid[valid_cells, :16].flatten().astype(np.float64)
        att_Y_vis = att_sigs[valid_cells, :16].flatten().astype(np.float64)

        std_ref_vis = float(np.std(ref_Y_vis))
        std_att_vis = float(np.std(att_Y_vis))
        if std_ref_vis > 1.0 and std_att_vis > 1.0:
            global_corr = float(
                np.mean((ref_Y_vis - np.mean(ref_Y_vis)) * (att_Y_vis - np.mean(att_Y_vis)))
                / (std_ref_vis * std_att_vis)
            )
        else:
            global_corr = 0.0

        ref_cells_y = ref_y_eff_grid[valid_cells, :16].astype(np.float64)
        att_cells_y = att_sigs[valid_cells, :16].astype(np.float64)
        ref_zm_cells = (ref_cells_y - np.mean(ref_cells_y, axis=1, keepdims=True)).flatten()
        att_zm_cells = (att_cells_y - np.mean(att_cells_y, axis=1, keepdims=True)).flatten()
        denom_zm = float(np.linalg.norm(ref_zm_cells) * np.linalg.norm(att_zm_cells))
        local_struct_corr = float(np.dot(ref_zm_cells, att_zm_cells) / denom_zm) if denom_zm > 1e-6 else 0.0

        # Compute aligned Sobel Edge Silhouette Correlation across visible mask (invariant to solarize/invert filters)
        edge_silhouette_corr = 0.0
        if ref_can_bgr is not None and ref_can_bgr.shape[:2] == (canonical_h, canonical_w):
            ew = 256
            eh = max(144, int(round(256.0 * canonical_h / max(canonical_w, 1))))
            r_sm = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(ref_can_bgr, (ew, eh)), cv2.COLOR_BGR2GRAY), (7, 7), 1.8).astype(np.float32)
            a_sm = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(rectified, (ew, eh)), cv2.COLOR_BGR2GRAY), (7, 7), 1.8).astype(np.float32)
            m_sm = cv2.erode(cv2.resize(raw_cov_mask, (ew, eh), interpolation=cv2.INTER_NEAREST), np.ones((7, 7), np.uint8)) > 127
            if int(np.sum(m_sm)) >= 48:
                re_m = np.hypot(cv2.Sobel(r_sm, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(r_sm, cv2.CV_32F, 0, 1, ksize=3))[m_sm]
                ae_m = np.hypot(cv2.Sobel(a_sm, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(a_sm, cv2.CV_32F, 0, 1, ksize=3))[m_sm]
                if float(np.std(re_m)) > 1.0 and float(np.std(ae_m)) > 1.0:
                    edge_silhouette_corr = float(np.mean((re_m - np.mean(re_m)) * (ae_m - np.mean(ae_m))) / (np.std(re_m) * np.std(ae_m)))

        std_zm_ref = float(np.std(ref_zm_cells))
        std_zm_att = float(np.std(att_zm_cells))
        min_lcorr = 0.62 if matched_via == "STRUCTURAL_PYRAMID_PATH_C" else 0.52
        min_std_ratio = 0.38
        filter_candidate = bool(
            not grayscale_detected
            and edge_silhouette_corr >= 0.34
            and (global_corr < 0.30 or local_struct_corr < min_lcorr)
        )
        filter_edit_detected = False

        if has_colored_marker and (global_corr < 0.30 or local_struct_corr < min_lcorr):
            rect_clean = cv2.warpPerspective(
                query_clean_bgr, H_mat, (canonical_w, canonical_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)
            )
            sigs_clean = self.compute_canonical_signature(rect_clean, canonical_w, canonical_h, valid_mask_u8=raw_cov_mask)
            ay_c_vis = sigs_clean[valid_cells, :16].flatten().astype(np.float64)
            if float(np.std(ay_c_vis)) > 1.0 and std_ref_vis > 1.0:
                g_corr_c = float(np.mean((ref_Y_vis - np.mean(ref_Y_vis)) * (ay_c_vis - np.mean(ay_c_vis))) / (std_ref_vis * float(np.std(ay_c_vis))))
                ac_y = sigs_clean[valid_cells, :16].astype(np.float64)
                azm_c = (ac_y - np.mean(ac_y, axis=1, keepdims=True)).flatten()
                dzm_c = float(np.linalg.norm(ref_zm_cells) * np.linalg.norm(azm_c))
                l_corr_c = float(np.dot(ref_zm_cells, azm_c) / dzm_c) if dzm_c > 1e-6 else 0.0
                if g_corr_c >= 0.30 and l_corr_c >= 0.45:
                    global_corr = max(global_corr, g_corr_c)
                    local_struct_corr = max(local_struct_corr, l_corr_c)
                    marker_suppression_used = True

        # Never bail out when watermark decoded, micro-crop locked, or edge silhouette locked under artistic filter
        is_verified_subcrop = bool(
            matched_via == "STRUCTURAL_PYRAMID_PATH_C"
            and structural_corr >= 0.56
            and float(np.mean(raw_cov_mask > 127)) < 0.45
            and global_corr >= 0.25
        )
        if (
            not wm_decoded_for_this_ref
            and matched_via != "MICRO_CROP_TEMPLATE_LOCK"
            and not is_verified_subcrop
            and not marker_suppression_used
            and not filter_candidate
            and (
                global_corr < 0.30
                or local_struct_corr < min_lcorr
                or (std_zm_ref > 4.0 and std_zm_att / std_zm_ref < min_std_ratio)
            )
        ):
            return self._unmatched_response(
                query_bgr,
                ref_pts,
                ref_sigs,
                canonical_w,
                canonical_h,
                wm_decoded_for_this_ref,
                wm_surviving_tiles,
                inliers=0,
                inlier_ratio=0.0,
                structural_corr=structural_corr,
                wm_tile_survival_pct=wm_tile_survival_pct,
            )

        if structural_corr == 0.0:
            structural_corr = round(0.5 * global_corr + 0.5 * local_struct_corr, 3)

        non_clipped = (att_Y_vis > 8.0) & (att_Y_vis < 247.0)
        if np.sum(non_clipped) >= 64:
            ref_Y_fit = ref_Y_vis[non_clipped]
            att_Y_fit = att_Y_vis[non_clipped]
        else:
            ref_Y_fit = ref_Y_vis
            att_Y_fit = att_Y_vis

        if bw_regression_active:
            scale_a = 1.0
            offset_b = 0.0
            inv_scale_a = 1.0
            fwd_offset_b = 0.0
        else:
            iqr_att_y = max(
                float(np.percentile(att_Y_fit, 75) - np.percentile(att_Y_fit, 25)), 1.0
            )
            scale_a = float(
                np.clip(
                    (np.percentile(ref_Y_fit, 75) - np.percentile(ref_Y_fit, 25)) / iqr_att_y,
                    0.35,
                    2.60,
                )
            )
            offset_b = float(np.median(ref_Y_fit - scale_a * att_Y_fit))
            inv_scale_a = 1.0 / max(scale_a, 0.15)
            fwd_offset_b = -offset_b * inv_scale_a

        rect_ycrcb = cv2.cvtColor(rectified, cv2.COLOR_BGR2YCrCb).astype(np.float64)
        rect_ycrcb[:, :, 0] = np.clip(scale_a * rect_ycrcb[:, :, 0] + offset_b, 0.0, 255.0)
        rectified_cal_bgr = cv2.cvtColor(rect_ycrcb.astype(np.uint8), cv2.COLOR_YCrCb2BGR)

        iqr_att_cr = max(float(np.percentile(att_Cr_vis, 75) - np.percentile(att_Cr_vis, 25)), 1.5)
        scale_cr = float(
            np.clip(
                (np.percentile(ref_Cr_vis, 75) - np.percentile(ref_Cr_vis, 25)) / iqr_att_cr,
                0.50,
                2.00,
            )
        )
        offset_cr = float(np.median(ref_Cr_vis - scale_cr * att_Cr_vis))

        iqr_att_cb = max(float(np.percentile(att_Cb_vis, 75) - np.percentile(att_Cb_vis, 25)), 1.5)
        scale_cb = float(
            np.clip(
                (np.percentile(ref_Cb_vis, 75) - np.percentile(ref_Cb_vis, 25)) / iqr_att_cb,
                0.50,
                2.00,
            )
        )
        offset_cb = float(np.median(ref_Cb_vis - scale_cb * att_Cb_vis))

        w_y = 1.0 if grayscale_detected else 0.80
        w_c = 0.0 if grayscale_detected else 0.20

        anomaly_scores = np.zeros((self.grid_n, self.grid_n), dtype=np.float64)
        for gy in range(self.grid_n):
            y0, y1 = gy * cell_h, (gy + 1) * cell_h
            for gx in range(self.grid_n):
                x0, x1 = gx * cell_w, (gx + 1) * cell_w
                if valid_cells[gy, gx]:
                    r_y = ref_y_eff_grid[gy, gx, :16].astype(np.float64)
                    a_y = att_sigs[gy, gx, :16].astype(np.float64)

                    att_y_cal = np.clip(scale_a * a_y + offset_b, 0.0, 255.0)
                    diff_inv = np.abs(r_y - att_y_cal)

                    ref_y_fwd = np.clip(inv_scale_a * r_y + fwd_offset_b, 0.0, 255.0)
                    diff_fwd = np.abs(a_y - ref_y_fwd) * min(scale_a, 1.0)

                    sub_diffs = np.minimum(diff_inv, diff_fwd) / 255.0
                    y_diff = float(np.sqrt(np.mean(sub_diffs ** 2)))
                    p95_y_sub = float(np.percentile(sub_diffs, 95))
                    y_diff = max(y_diff, 0.70 * p95_y_sub)

                    att_cr_cal = scale_cr * att_sigs[gy, gx, 16] + offset_cr
                    att_cb_cal = scale_cb * att_sigs[gy, gx, 17] + offset_cb
                    c_diff = float(
                        np.sqrt(
                            0.5 * ((ref_sigs[gy, gx, 16] - att_cr_cal) ** 2 + (ref_sigs[gy, gx, 17] - att_cb_cal) ** 2)
                        )
                    ) / 255.0

                    p95_c_diff = c_diff
                    if ref_smooth_ycrcb is not None and att_smooth_ycrcb is not None and not grayscale_detected:
                        a_y_p = att_smooth_ycrcb[y0:y1, x0:x1, 0]
                        r_cr_p = ref_smooth_ycrcb[y0:y1, x0:x1, 1]
                        r_cb_p = ref_smooth_ycrcb[y0:y1, x0:x1, 2]
                        a_cr_p = scale_cr * att_smooth_ycrcb[y0:y1, x0:x1, 1] + offset_cr
                        a_cb_p = scale_cb * att_smooth_ycrcb[y0:y1, x0:x1, 2] + offset_cb
                        pix_c_diff = np.sqrt(0.5 * ((r_cr_p - a_cr_p) ** 2 + (r_cb_p - a_cb_p) ** 2)) / 255.0
                        r_sat = np.hypot(r_cr_p - 128.0, r_cb_p - 128.0)
                        a_sat = np.hypot(att_smooth_ycrcb[y0:y1, x0:x1, 1] - 128.0, att_smooth_ycrcb[y0:y1, x0:x1, 2] - 128.0)
                        marker_ink_mask = (a_sat > r_sat + 24.0) & (a_sat > 45.0) & (a_y_p < 225.0)
                        pix_c_diff = np.where(marker_ink_mask, pix_c_diff, 0.0)
                        p95_c_diff = float(np.percentile(pix_c_diff, 95))
                        if p95_c_diff > 0.15:
                            c_diff = max(c_diff, 0.85 * p95_c_diff)

                    std_r = float(np.std(r_y))
                    std_a = float(np.std(a_y))
                    if std_r > 1.5 and std_a > 1.5 and c_diff < 0.15 and p95_c_diff < 0.16:
                        r_norm = (r_y - float(np.mean(r_y))) / std_r
                        a_norm = (a_y - float(np.mean(a_y))) / std_a
                        corr_cell = float(np.mean(r_norm * a_norm))
                        if corr_cell > 0.65:
                            r_zm = r_y - float(np.mean(r_y))
                            a_zm = att_y_cal - float(np.mean(att_y_cal))
                            struct_diff = float(np.sqrt(np.mean((r_zm - a_zm) ** 2))) / 255.0
                            y_diff = min(y_diff, struct_diff * (1.0 - 0.5 * corr_cell))
                            c_diff = c_diff * (1.0 - 0.4 * corr_cell)

                    base_anom = w_y * y_diff + w_c * c_diff
                    if not grayscale_detected and p95_c_diff > 0.15:
                        base_anom = max(base_anom, 0.72 * p95_c_diff + 0.28 * y_diff)
                    anomaly_scores[gy, gx] = base_anom

        raw_median_score = float(np.median(anomaly_scores[valid_cells]))

        # Subtract smooth 5x5 neighborhood screen-glare excess without shrinking baseline MAD
        smooth_bg = cv2.GaussianBlur(anomaly_scores.astype(np.float32), (5, 5), 1.5)
        q25_score = float(np.percentile(anomaly_scores[valid_cells], 25))
        glare_trend = np.maximum(0.0, smooth_bg - raw_median_score)
        local_anom = np.maximum(0.0, anomaly_scores - 0.55 * glare_trend)
        vis_scores = local_anom[valid_cells]

        # Use lower-65% clean subset for MAD when heavy scribbles cover 35-55% of the image
        p65 = float(np.percentile(vis_scores, 65))
        clean_sub = vis_scores[vis_scores <= p65] if np.sum(vis_scores <= p65) >= 8 else vis_scores
        median_score = float(np.median(clean_sub))
        mad = float(np.median(np.abs(clean_sub - median_score)))
        robust_sigma = max(1.4826 * mad, 0.0125)

        z_grid = np.zeros((self.grid_n, self.grid_n), dtype=np.float64)
        z_grid[valid_cells] = (local_anom[valid_cells] - median_score) / robust_sigma

        tampered_mask = valid_cells & (z_grid > 5.8) & (local_anom > 0.062)

        # Fix 3 (Heavy Marker Scribbles): If watermark locked with localized tile damage (12% <= tile_survival_pct <= 92%),
        # include high-anomaly cells and damaged tile coordinates so heavy black marker scribbles light up on the Change Map!
        if wm_decoded_for_this_ref and 12.0 <= wm_tile_survival_pct <= 92.0:
            heavy_scribble_mask = valid_cells & (anomaly_scores > max(0.14, q25_score + 0.10))
            if int(np.sum(heavy_scribble_mask)) >= 3:
                tampered_mask = tampered_mask | heavy_scribble_mask
                if wm_damaged_grid_coords:
                    for gy_d, gx_d in wm_damaged_grid_coords:
                        if 0 <= gy_d < self.grid_n and 0 <= gx_d < self.grid_n:
                            if valid_cells[gy_d, gx_d] and anomaly_scores[gy_d, gx_d] > max(0.095, q25_score + 0.065):
                                tampered_mask[gy_d, gx_d] = True

        # If marker_suppression_used is True, isolate all cells containing colored marker scribbles
        # Fix 3 (Extreme Artistic / Solarize Filter): Global color/tone shift where brightness/structure is inverted (filter_candidate)
        if (
            not grayscale_detected
            and not marker_suppression_used
            and float(np.mean(raw_cov_mask > 127)) >= 0.25
            and edge_silhouette_corr >= 0.34
            and q25_score > 0.035
            and filter_candidate
        ):
            filter_edit_detected = True

        if (marker_suppression_used or (has_colored_marker and float(np.max(z_grid[valid_cells])) > 4.5)) and not filter_edit_detected:
            marker_cell_mask = valid_cells & (anomaly_scores > max(0.065, q25_score + 0.030))
            if int(np.sum(marker_cell_mask)) >= 3 and raw_median_score > 0.025:
                tampered_mask = tampered_mask | marker_cell_mask

        if filter_edit_detected:
            # Global color/artistic filter shifts the whole image rather than a localized splice
            tampered_mask[:] = False
            structural_corr = max(float(structural_corr), round(float(edge_silhouette_corr), 3))

        tampered_coords = [[int(r), int(c)] for r, c in zip(*np.where(tampered_mask))]

        # Fix 4: Detect AI Outpainting / Expanded Corners & Borders
        area_cov_pct = round(100.0 * float(np.mean(raw_cov_mask > 127)), 1)
        qh_curr, qw_curr = query_bgr.shape[:2]
        outpainted_detected = False
        outpainted_expansion_pct = 0.0
        in_ref_mask_on_query = None
        try:
            H_inv = np.linalg.inv(H_mat)
            ones_ref = np.full((canonical_h, canonical_w), 255, dtype=np.uint8)
            in_ref_mask_on_query = cv2.warpPerspective(
                ones_ref, H_inv, (qw_curr, qh_curr), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0
            )
            inside_ratio = float(np.mean(in_ref_mask_on_query > 127))
            outpainted_frac = 1.0 - inside_ratio
            if outpainted_frac >= 0.12 and area_cov_pct >= 68.0 and local_struct_corr >= 0.55 and global_corr >= 0.40:
                outpainted_detected = True
                outpainted_expansion_pct = round(outpainted_frac * 100.0, 1)
        except np.linalg.LinAlgError:
            pass

        cal_diff_direct = self._compute_calibrated_direct_diff(ref_sigs, att_sigs)
        is_transplant = bool(
            wm_decoded_for_this_ref
            and wm_surviving_tiles >= 6
            and area_cov_pct >= 50.0
            and wm_tile_survival_pct >= 82.0
            and matched_via != "MICRO_CROP_TEMPLATE_LOCK"
            and not filter_edit_detected
            and not outpainted_detected
            and (
                (cal_diff_direct > 0.35 and (inliers < 12 or raw_median_score > 0.08))
                or (local_struct_corr < 0.22 and global_corr < 0.22)
            )
        )

        if is_verified_subcrop and raw_median_score < 0.08:
            tampered_coords = []
        diffusion_regenerated = bool(
            matched_via == "STRUCTURAL_PYRAMID_PATH_C"
            and not is_verified_subcrop
            and not wm_decoded_for_this_ref
            and not grayscale_detected
            and not filter_edit_detected
            and not outpainted_detected
            and (raw_median_score >= 0.09 or len(tampered_coords) > 0)
        )

        return {
            "matched": True,
            "matched_via": matched_via,
            "inliers": inliers,
            "inlier_ratio": round(inlier_ratio, 3),
            "structural_corr": round(structural_corr, 3),
            "coverage_pct": area_cov_pct,
            "median_anomaly": round(raw_median_score, 4),
            "max_z_mad": round(float(np.max(z_grid[valid_cells])), 2),
            "num_tampered_cells": len(tampered_coords),
            "tampered_coords": tampered_coords,
            "transplant_forgery": is_transplant,
            "diffusion_regenerated": diffusion_regenerated,
            "filter_edit_detected": filter_edit_detected,
            "outpainted_detected": outpainted_detected,
            "outpainted_expansion_pct": outpainted_expansion_pct,
            "in_ref_mask_on_query": in_ref_mask_on_query,
            "query_oriented_bgr": query_bgr,
            "grayscale_detected": grayscale_detected,
            "detected_orientation_code": orient_code,
            "detected_orientation_label": DIHEDRAL_LABELS.get(orient_code, "0° Normal"),
            "photometric_scale_a": round(scale_a, 3),
            "photometric_offset_b": round(offset_b, 2),
            "rectified_bgr": rectified,
            "rectified_cal_bgr": rectified_cal_bgr,
            "coverage_mask": raw_cov_mask,
            "z_grid": z_grid,
        }
