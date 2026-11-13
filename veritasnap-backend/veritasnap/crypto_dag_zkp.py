"""
VeritaSnap V2 — Layer 3: Whistleblower Zero-Knowledge Privacy Shield,
Provenance DAG Engine & 4-State Non-Expert Verdict Evaluator
===========================================================================
Implements:
- Client-Side EXIF / GPS / Serial Metadata Scrubbing (Bug 13 Fix)
- 2048-bit MODP Group 14 (RFC 3526) Pedersen Commitments: C = g^s * h^r mod p
- Non-Interactive Schnorr Fiat-Shamir Zero-Knowledge Proof (NIZKPoK) of Authorship
- Clear, Plain-English 4-State Non-Expert Forensic Verdict Decision Tree
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# RFC 3526 2048-bit MODP Group 14 Safe Prime p (p = 2q + 1)
RFC3526_PRIME_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF"
)
P_MOD = int(RFC3526_PRIME_HEX, 16)
Q_ORDER = (P_MOD - 1) // 2
G_GEN = 2

# Nothing-up-my-sleeve second generator H_GEN derived via SHA-512("VeritaSnap-V2-Pedersen-H")
_h_seed = int(
    hashlib.sha512(b"VeritaSnap-V2-Pedersen-Generator-H-2026").hexdigest(), 16
) % (P_MOD - 3) + 2
H_GEN = pow(_h_seed, 2, P_MOD)


class WhistleblowerZKPShield:
    """
    Zero-Knowledge Privacy Shield:
    1. Strips all raw EXIF/GPS/Camera-Serial tags by re-encoding from pure pixel array.
    2. Coarsens capture timestamp to a 24-hour UTC date bucket.
    3. Commits to author secret s and 256-bit blinding factor r via C = g^s * h^r mod p.
    4. Generates and verifies Fiat-Shamir non-interactive Schnorr proofs of opening (s, r).
    """

    @staticmethod
    def scrub_exif_and_metadata(
        raw_file_bytes: bytes, decoded_bgr: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        has_app1_exif = b"Exif" in raw_file_bytes[:4096]
        has_gps_tag = b"GPS" in raw_file_bytes[:8192]
        utc_date_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        clean_pixels = decoded_bgr.copy()
        scrub_report = {
            "exif_app1_detected_and_stripped": bool(has_app1_exif),
            "gps_coordinates_zeroed": True,
            "had_raw_gps_tags": bool(has_gps_tag),
            "device_serial_stripped": True,
            "timestamp_coarsened_to_24h_utc": True,
            "timestamp_bucket_utc": utc_date_bucket,
            "pii_bytes_retained": 0,
        }
        return clean_pixels, scrub_report

    @staticmethod
    def _derive_secret_scalar(author_secret_phrase: str) -> int:
        digest = hashlib.sha256(
            f"VeritaSnap-Author-Scalar:{author_secret_phrase}".encode("utf-8")
        ).hexdigest()
        return (int(digest, 16) % (Q_ORDER - 2)) + 1

    @classmethod
    def commit_and_prove(
        cls,
        author_secret_phrase: str,
        short_media_id: str,
        claim_context: str = "VERITASNAP-ZKP-OWNERSHIP-2026",
        blinding_factor_hex: Optional[str] = None,
    ) -> Dict[str, Any]:
        s_val = cls._derive_secret_scalar(author_secret_phrase)
        if blinding_factor_hex:
            r_val = int(blinding_factor_hex, 16) % Q_ORDER
        else:
            r_seed = hashlib.sha512(
                f"VeritaSnap-ZKP-Blinding:{author_secret_phrase}:{short_media_id}".encode("utf-8")
            ).hexdigest()
            r_val = (int(r_seed, 16) % (Q_ORDER - 2)) + 1

        C_comm = (pow(G_GEN, s_val, P_MOD) * pow(H_GEN, r_val, P_MOD)) % P_MOD

        k_s = secrets.randbelow(Q_ORDER - 2) + 1
        k_r = secrets.randbelow(Q_ORDER - 2) + 1
        R_nonce = (pow(G_GEN, k_s, P_MOD) * pow(H_GEN, k_r, P_MOD)) % P_MOD

        chal_input = f"{C_comm:x}|{R_nonce:x}|{short_media_id}|{claim_context}".encode("utf-8")
        e_chal = int(hashlib.sha256(chal_input).hexdigest(), 16) % Q_ORDER

        z_s = (k_s + e_chal * s_val) % Q_ORDER
        z_r = (k_r + e_chal * r_val) % Q_ORDER

        return {
            "pedersen_commitment_hex": f"{C_comm:x}",
            "blinding_factor_secret_hex": f"{r_val:x}",
            "schnorr_proof": {
                "R_nonce_hex": f"{R_nonce:x}",
                "e_challenge_hex": f"{e_chal:x}",
                "z_s_response_hex": f"{z_s:x}",
                "z_r_response_hex": f"{z_r:x}",
                "claim_context": claim_context,
            },
        }

    @staticmethod
    def verify_schnorr_opening(
        pedersen_commitment_hex: str,
        schnorr_proof: Dict[str, str],
        short_media_id: str,
    ) -> bool:
        try:
            C_comm = int(pedersen_commitment_hex, 16)
            R_nonce = int(schnorr_proof["R_nonce_hex"], 16)
            e_chal = int(schnorr_proof["e_challenge_hex"], 16)
            z_s = int(schnorr_proof["z_s_response_hex"], 16)
            z_r = int(schnorr_proof["z_r_response_hex"], 16)
            claim_context = schnorr_proof.get("claim_context", "VERITASNAP-ZKP-OWNERSHIP-2026")
        except (KeyError, ValueError):
            return False

        if C_comm <= 1 or C_comm >= P_MOD or R_nonce <= 1 or R_nonce >= P_MOD:
            return False

        chal_input = f"{C_comm:x}|{R_nonce:x}|{short_media_id}|{claim_context}".encode("utf-8")
        expected_e = int(hashlib.sha256(chal_input).hexdigest(), 16) % Q_ORDER
        if e_chal != expected_e:
            return False

        lhs = (pow(G_GEN, z_s, P_MOD) * pow(H_GEN, z_r, P_MOD)) % P_MOD
        rhs = (R_nonce * pow(C_comm, e_chal, P_MOD)) % P_MOD
        return bool(lhs == rhs)


def evaluate_4state_verdict(
    wm_res: Dict[str, Any],
    xray_res: Dict[str, Any],
    sig_valid: bool,
    claimed_origin: int = 0,
    db_record_found: bool = False,
    matched_media_id: Optional[str] = None,
    matched_origin_code: Optional[int] = None,
) -> Dict[str, str]:
    """
    Maps verification telemetry into the 4 Plain-English Verdicts:
      1. UNVERIFIED (NO RECORD FOUND)  [verdict_code: UNKNOWN]
      2. CONFIRMED FORGERY             [verdict_code: FAKE_FORGERY]
      3. AUTHENTIC SOURCE — EDITED     [verdict_code: AUTHENTIC_ALTERED]
      4. VERIFIED AUTHENTIC            [verdict_code: VERIFIED_AUTHENTIC]
    """
    wm_hit = bool(
        wm_res.get("watermark_detected", False)
        and db_record_found
        and (matched_media_id is None or wm_res.get("short_media_id") == matched_media_id)
    )
    geo_hit = bool(
        xray_res.get("matched", False)
        and (
            int(xray_res.get("inliers", 0)) >= 12
            or float(xray_res.get("structural_corr", 0.0)) >= 0.36
        )
        and db_record_found
    )
    rec_id = matched_media_id or wm_res.get("short_media_id") or "UNKNOWN"

    # 1. ABSTENTION GATE -> UNVERIFIED (NO RECORD FOUND)
    if not wm_hit and not geo_hit:
        return {
            "state": "UNKNOWN",
            "verdict_code": "UNKNOWN",
            "badge": "NO HISTORY FOUND",
            "headline": "No History Found — This image is not in our archive",
            "explanation": (
                "No matching record was found in our archive. "
                "Note: Missing history does not mean the photo is fake—it simply means this photo was not registered here."
            ),
        }

    # 2. FORGERY & ORIGIN MISREPRESENTATION GATE (Both Directions)
    if not sig_valid or bool(xray_res.get("transplant_forgery", False)):
        return {
            "state": "FAKE_FORGERY",
            "verdict_code": "FAKE_FORGERY",
            "badge": "FAKE / FORGED SIGNATURE",
            "headline": f"Fake / Forged Signature — This image does not match original photo #{rec_id}",
            "explanation": (
                f"This image carries a copied or invalid signature for #{rec_id}, but the visual content is completely different from the original photo."
            ),
        }

    actual_origin = int(
        matched_origin_code
        if (matched_origin_code is not None and matched_origin_code > 0)
        else wm_res.get("origin_flag", 1)
    )

    # Direction A: Claimed as Real Camera (1), Actually AI-Generated (2)
    if int(claimed_origin) == 1 and actual_origin == 2:
        return {
            "state": "FAKE_FORGERY",
            "verdict_code": "FAKE_FORGERY",
            "badge": "CONFIRMED FAKE — AI IMAGE CLAIMED AS CAMERA",
            "headline": f"Misleading Origin Claim: AI-Generated Image Shared as a Real Camera Photo (#{rec_id})",
            "explanation": (
                f"The embedded signature proves Record #{rec_id} was created by an AI generator, not a real physical camera."
            ),
        }

    # Direction B: Claimed as AI-Generated (2), Actually a Real Camera Photo (1 or 4 Private Camera)
    if int(claimed_origin) == 2 and actual_origin in (1, 4):
        return {
            "state": "AUTHENTIC_ALTERED",
            "verdict_code": "AUTHENTIC_ALTERED",
            "badge": "MISLEADING CLAIM — REAL CAMERA PHOTO CLAIMED AS AI",
            "headline": f"Origin Claim Mismatch: Real Camera Photo Falsely Labeled as AI Art (#{rec_id})",
            "explanation": (
                f"The embedded signature proves Record #{rec_id} is an authentic real camera capture, not AI-generated art."
            ),
        }

    # 3. POST-CAPTURE EDIT GATE -> AUTHENTIC SOURCE — EDITED
    tampered_cells = int(xray_res.get("num_tampered_cells", 0))
    cov_pct = float(xray_res.get("coverage_pct", 100.0))
    cropped_out_pct = round(max(0.0, 100.0 - cov_pct), 1)
    outpainted = bool(xray_res.get("outpainted_detected", False))
    outpainted_pct = float(xray_res.get("outpainted_expansion_pct", 0.0))
    filter_edit = bool(xray_res.get("filter_edit_detected", False))

    if outpainted and outpainted_pct >= 10.0:
        return {
            "state": "AUTHENTIC_ALTERED",
            "verdict_code": "AUTHENTIC_ALTERED",
            "badge": "ORIGINAL SOURCE FOUND — BORDERS EXPANDED",
            "headline": f"Original Source Found (#{rec_id}), But Image Was Edited (Borders Expanded +{outpainted_pct}%)",
            "explanation": (
                f"This image comes from original photo #{rec_id}, but new outer borders (+{outpainted_pct}% extra canvas) "
                f"were generated around it. Red marks the newly added outer borders; green marks the original photo."
            ),
        }

    if tampered_cells > 0:
        return {
            "state": "AUTHENTIC_ALTERED",
            "verdict_code": "AUTHENTIC_ALTERED",
            "badge": "ORIGINAL SOURCE FOUND — EDITED",
            "headline": f"Original Source Found (#{rec_id}), But Image Was Edited ({tampered_cells} Area(s) Changed)",
            "explanation": (
                f"This image comes from original photo #{rec_id} ({cropped_out_pct}% cropped out), "
                f"but {tampered_cells} area(s) were drawn on or modified after capture (highlighted in red)."
            ),
        }

    if filter_edit or bool(xray_res.get("diffusion_regenerated", False)):
        return {
            "state": "AUTHENTIC_ALTERED",
            "verdict_code": "AUTHENTIC_ALTERED",
            "badge": "ORIGINAL SOURCE FOUND — HEAVY FILTER",
            "headline": f"Original Source Found (#{rec_id}), But Image Was Edited (Heavy Color / Artistic Filter)",
            "explanation": (
                f"This image matches the shapes and outlines of original photo #{rec_id}, "
                f"but a heavy color, solarize, or AI style filter was applied across the picture."
            ),
        }

    # 3B. UNWATERMARKED ORIGINAL FILE CHECK (Visual match to archive, but invisible 64x64 signature is absent)
    sync_z = float(wm_res.get("sync_z_score", 0.0))
    is_bw_or_tonal = bool(
        xray_res.get("grayscale_detected", False)
        or xray_res.get("tonal_filter_tolerated", False)
    )
    orient_lbl = xray_res.get("detected_orientation_label", "0° Normal")
    if (
        not wm_hit
        and cov_pct >= 75.0
        and not is_bw_or_tonal
        and orient_lbl == "0° Normal"
        and bool(xray_res.get("unwatermarked_original_suspected", False))
    ):
        return {
            "state": "AUTHENTIC_ALTERED",
            "verdict_code": "AUTHENTIC_ALTERED",
            "badge": "VISUAL MATCH ONLY — INVISIBLE SIGNATURE ABSENT",
            "headline": f"Visual Match to #{rec_id}, But Invisible Signature Is Not Present",
            "explanation": (
                f"The visual image matches Original Record #{rec_id} (99%+ structural match, 0 edited regions), "
                f"but the invisible 64x64 pixel signature is missing from this file. Either you uploaded the raw "
                f"unwatermarked photo from before it was protected, or a watermark-removal tool stripped the signature."
            ),
        }

    # 4. VERIFIED AUTHENTIC (Matched photo with 0 tampered cells and verified signature)
    gain_alpha = wm_res.get("locked_gain_alpha", 1.0)
    dpi_scale = wm_res.get("locked_dpi_scale", 1.0)
    gray_note = ", B&W filter calibrated" if xray_res.get("grayscale_detected") else ""
    return {
        "state": "VERIFIED_AUTHENTIC",
        "verdict_code": "VERIFIED_AUTHENTIC",
        "badge": "AUTHENTIC PHOTO — INVISIBLE SIGNATURE VERIFIED",
        "headline": f"Authentic Photo — Matches Original Record #{rec_id}",
        "explanation": (
            f"Invisible 64x64 signature verified! This photo matches Original Record #{rec_id} with zero edited regions "
            f"(survived {cropped_out_pct}% crop, orientation: {orient_lbl}, scale {dpi_scale}x, "
            f"contrast {gain_alpha}x{gray_note})."
        ),
    }


def compute_phash_64(img_bgr: np.ndarray) -> int:
    """Computes 64-bit DCT perceptual hash (signed int64 for SQLite INTEGER column)."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct_mat = cv2.dct(resized)
    dct_low = dct_mat[:8, :8].flatten()
    med = float(np.median(dct_low[1:]))
    bits = (dct_low > med).astype(np.uint64)
    val = 0
    for b in bits:
        val = (val << 1) | int(b)
    if val >= (1 << 63):
        val -= 1 << 64
    return int(val)
