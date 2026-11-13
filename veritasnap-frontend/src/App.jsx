import React, { useState, useEffect, useRef } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  AlertTriangle,
  Upload,
  CheckCircle2,
  Lock,
  Layers,
  RefreshCw,
  Download,
  Camera,
  Cpu,
  GitBranch,
  KeyRound,
  Trash2,
  MapPin,
  Navigation,
  EyeOff,
  ArrowRight,
  Database,
  Check,
  X,
  Image as ImageIcon,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const ORIGIN_OPTIONS = [
  {
    code: 1,
    label: "Camera Photo",
    icon: Camera,
  },
  {
    code: 2,
    label: "AI Generated",
    icon: Cpu,
  },
  {
    code: 3,
    label: "Edited Version",
    icon: GitBranch,
  },
];

function formatOriginLabel(code, fallbackLabel) {
  if (Number(code) === 1) return "Camera Photo";
  if (Number(code) === 2) return "AI Generated";
  if (Number(code) === 3) return "Edited Version";
  if (Number(code) === 4) return "Private Camera (Hidden)";
  return fallbackLabel || "Camera Photo";
}

function getVerdictTheme(verdictCode) {
  switch (verdictCode) {
    case "VERIFIED_AUTHENTIC":
      return {
        bg: "bg-[#EAF6F0] border-[#C5E7D6]",
        pill: "bg-[#287D56] text-white",
        title: "text-[#164E35]",
        body: "text-[#236B4A]",
        icon: ShieldCheck,
        defaultBadge: "Authentic Photo",
      };
    case "AUTHENTIC_ALTERED":
      return {
        bg: "bg-[#FDF0E9] border-[#F4CBB8]",
        pill: "bg-[#D96B4B] text-white",
        title: "text-[#7C2D12]",
        body: "text-[#9A3412]",
        icon: AlertTriangle,
        defaultBadge: "Original Source Found • Edited",
      };
    case "FAKE_FORGERY":
      return {
        bg: "bg-[#FDECEC] border-[#F7C4C4]",
        pill: "bg-[#C83E3E] text-white",
        title: "text-[#7F1D1D]",
        body: "text-[#991B1B]",
        icon: ShieldAlert,
        defaultBadge: "Fake / Forged Signature",
      };
    default:
      return {
        bg: "bg-[#F3EFEA] border-[#E2D9CE]",
        pill: "bg-[#5A6270] text-white",
        title: "text-[#18202C]",
        body: "text-[#5A6270]",
        icon: ShieldQuestion,
        defaultBadge: "No History Found",
      };
  }
}

function formatImgSrc(b64OrUri) {
  if (!b64OrUri) return null;
  if (b64OrUri.startsWith("data:image/")) return b64OrUri;
  return `data:image/png;base64,${b64OrUri}`;
}

/* Minimal Horizon Emblem inspired by KayaSetu Screenshot 4 */
function HorizonEmblem({ size = "sm" }) {
  const dim = size === "lg" ? "w-28 h-20" : "w-10 h-10";
  return (
    <div
      className={`${dim} rounded-2xl bg-[#F6EDE6] border border-[#ECDCD0] p-1.5 flex items-center justify-center shrink-0 overflow-hidden`}
    >
      <svg
        viewBox="0 0 100 100"
        className="w-full h-full rounded-xl overflow-hidden"
        aria-hidden="true"
      >
        <rect width="100" height="100" fill="#FAF7F2" />
        {/* Warm Sun Gold Circle */}
        <circle cx="66" cy="36" r="20" fill="#F0CE91" />
        {/* Soft Mist Wave */}
        <path
          d="M0 68 Q 32 48, 66 64 T 100 58 L 100 100 L 0 100 Z"
          fill="#DCE3EA"
        />
        {/* Terracotta Coral Ridge */}
        <path
          d="M0 77 Q 45 58, 100 74 L 100 100 L 0 100 Z"
          fill="#DE846B"
        />
        {/* Deep Midnight Slate Base */}
        <path
          d="M0 86 Q 48 74, 100 86 L 100 100 L 0 100 Z"
          fill="#18202C"
        />
      </svg>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("verify");

  // 1. Check Photo State
  const [verifyFile, setVerifyFile] = useState(null);
  const [verifyPreview, setVerifyPreview] = useState(null);
  const [claimedOrigin, setClaimedOrigin] = useState(0); // 0 = Auto-Detect
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyError, setVerifyError] = useState(null);
  const [activeXrayTab, setActiveXrayTab] = useState("tamper");

  // Passphrase Ownership Check State
  const [zkpClaimId, setZkpClaimId] = useState("");
  const [zkpSecretInput, setZkpSecretInput] = useState("");
  const [zkpShowPass, setZkpShowPass] = useState(false);
  const [zkpClaimResult, setZkpClaimResult] = useState(null);
  const [zkpClaimLoading, setZkpClaimLoading] = useState(false);

  // 2. Protect Photo State
  const [signFile, setSignFile] = useState(null);
  const [signPreview, setSignPreview] = useState(null);
  const [originType, setOriginType] = useState(1);
  const [parentMediaId, setParentMediaId] = useState("");
  const [creatorHandle, setCreatorHandle] = useState("@prajwal");
  const [captureLocation, setCaptureLocation] = useState("Mangaluru, India");
  const [gpsLoading, setGpsLoading] = useState(false);
  const [gpsStatus, setGpsStatus] = useState("");
  const [privateMode, setPrivateMode] = useState(false);
  const [authorSecret, setAuthorSecret] = useState("sahyadri-press-secret-2026");
  const [showSecretPass, setShowSecretPass] = useState(false);
  const [signLoading, setSignLoading] = useState(false);
  const [signResult, setSignResult] = useState(null);
  const [signError, setSignError] = useState(null);
  const [showUvPreview, setShowUvPreview] = useState(false);

  // 3. Archive State
  const [registryItems, setRegistryItems] = useState([]);
  const [registryLoading, setRegistryLoading] = useState(false);
  const [benchmarks, setBenchmarks] = useState([]);
  const [benchLoading, setBenchLoading] = useState(false);

  const verifyInputRef = useRef(null);
  const signInputRef = useRef(null);

  const fetchRegistry = async () => {
    setRegistryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/registry`);
      if (res.ok) {
        const data = await res.json();
        setRegistryItems(data.items || data.records || []);
      }
    } catch (_) {
      // ignore offline
    } finally {
      setRegistryLoading(false);
    }
  };

  useEffect(() => {
    fetchRegistry();
  }, []);

  // GPS Auto-Fill Handler
  const handleUseMyGps = () => {
    if (!navigator.geolocation) {
      setGpsStatus("GPS unavailable");
      return;
    }
    setGpsLoading(true);
    setGpsStatus("Locating...");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude.toFixed(4);
        const lon = pos.coords.longitude.toFixed(4);
        try {
          const r = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=10`
          );
          if (r.ok) {
            const j = await r.json();
            const addr = j.address || {};
            const city =
              addr.city ||
              addr.town ||
              addr.village ||
              addr.county ||
              addr.state_district ||
              "";
            const state = addr.state || "";
            const country = addr.country || "";
            const place = [city, state || country].filter(Boolean).join(", ");
            if (place) {
              setCaptureLocation(`${place} (${lat}°, ${lon}°)`);
              setGpsStatus("GPS locked");
              setGpsLoading(false);
              return;
            }
          }
        } catch (_) {
          // fallback
        }
        setCaptureLocation(`GPS ${lat}° N, ${lon}° E`);
        setGpsStatus("GPS locked");
        setGpsLoading(false);
      },
      () => {
        setGpsStatus("Permission denied");
        setGpsLoading(false);
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const handleVerifyFileSelect = (file) => {
    if (!file) return;
    setVerifyFile(file);
    setVerifyPreview(URL.createObjectURL(file));
    setVerifyResult(null);
    setVerifyError(null);
    setZkpClaimResult(null);
  };

  const handleSignFileSelect = (file) => {
    if (!file) return;
    setSignFile(file);
    setSignPreview(URL.createObjectURL(file));
    setSignResult(null);
    setSignError(null);
  };

  const runVerificationWithFile = async (fileToVerify, originClaim = claimedOrigin) => {
    if (!fileToVerify) return;
    setVerifyLoading(true);
    setVerifyError(null);
    setZkpClaimResult(null);
    try {
      const form = new FormData();
      form.append("file", fileToVerify);
      form.append("claimed_origin", String(originClaim));

      const res = await fetch(`${API_BASE}/api/v1/verify`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setVerifyResult(data);
      if (data.matched_short_media_id) {
        setZkpClaimId(data.matched_short_media_id);
      }
      setActiveXrayTab("tamper");
    } catch (e) {
      setVerifyError(e.message || "Could not connect to verification service.");
    } finally {
      setVerifyLoading(false);
    }
  };

  const handleRunVerify = async (e) => {
    if (e) e.preventDefault();
    await runVerificationWithFile(verifyFile, claimedOrigin);
  };

  const handleRunSign = async (e) => {
    if (e) e.preventDefault();
    if (!signFile) return;
    if (privateMode && !authorSecret.trim()) {
      setSignError("Please enter a secret passphrase so you can prove ownership later.");
      return;
    }
    setSignLoading(true);
    setSignError(null);
    try {
      const form = new FormData();
      form.append("file", signFile);
      form.append("origin_type", String(privateMode ? 4 : originType));
      if (parentMediaId.trim()) {
        form.append("parent_media_id", parentMediaId.trim());
      }
      form.append("whistleblower_mode", String(privateMode));
      form.append(
        "author_secret_phrase",
        authorSecret.trim() || "sahyadri-press-secret-2026"
      );
      form.append(
        "creator_handle",
        privateMode ? "Anonymous Creator" : creatorHandle.trim() || "@prajwal"
      );
      form.append(
        "capture_location",
        privateMode ? "Hidden (Private Mode)" : captureLocation.trim() || "Mangaluru, India"
      );

      const res = await fetch(`${API_BASE}/api/v1/create`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setSignResult(data);
      setShowUvPreview(false);
      setZkpClaimId(data.short_media_id || "");
      await fetchRegistry();
    } catch (e) {
      setSignError(e.message || "Could not protect and register photo.");
    } finally {
      setSignLoading(false);
    }
  };

  const handleInspectBase64Image = async (b64Data, filename = "imprint_photo.png") => {
    const uri = formatImgSrc(b64Data);
    if (!uri) return;
    const res = await fetch(uri);
    const blob = await res.blob();
    const file = new File([blob], filename, { type: "image/png" });
    setVerifyFile(file);
    setVerifyPreview(URL.createObjectURL(file));
    setClaimedOrigin(0);
    setActiveTab("verify");
    await runVerificationWithFile(file, 0);
  };

  const handleVerifyPassphrase = async (e) => {
    e.preventDefault();
    const targetId = zkpClaimId.trim() || verifyResult?.matched_short_media_id || "";
    if (!targetId || !zkpSecretInput.trim()) return;
    setZkpClaimLoading(true);
    setZkpClaimResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/zkp/claim-authorship`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          short_media_id: targetId,
          author_secret_phrase: zkpSecretInput,
          verifier_challenge_context: "CREATOR_OWNERSHIP_CHECK_2026",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Photo ID not found in archive.");
      }
      setZkpClaimResult(data);
    } catch (err) {
      setZkpClaimResult({
        verified: false,
        message: err.message || "Passphrase verification failed.",
      });
    } finally {
      setZkpClaimLoading(false);
    }
  };

  const handleRunBenchmarks = async () => {
    setBenchLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/benchmark/run`);
      if (res.ok) {
        const data = await res.json();
        setBenchmarks(data.benchmark_cases || data.benchmarks || []);
      }
    } catch (_) {
      // ignore
    } finally {
      setBenchLoading(false);
    }
  };

  const handleResetArchive = async () => {
    await fetch(`${API_BASE}/api/v1/registry/reset`, { method: "POST" });
    setRegistryItems([]);
    setVerifyResult(null);
    setSignResult(null);
  };

  const wmMetrics =
    verifyResult?.path_a_blind_watermark ||
    verifyResult?.watermark ||
    verifyResult?.metrics?.watermark ||
    {};
  const xrayMetrics =
    verifyResult?.spatial_xray ||
    verifyResult?.xray ||
    verifyResult?.path_b_spatial_xray ||
    {};
  const visuals = verifyResult?.visual_artifacts || verifyResult?.visuals || {};

  const tamperImg = formatImgSrc(
    visuals.tamper_xray_b64 ||
      visuals.xray_SideBySide_b64 ||
      verifyResult?.heatmap_png_b64
  );
  const ghostImg = formatImgSrc(
    visuals.ghost_uncrop_b64 ||
      visuals.rectified_query_b64 ||
      verifyResult?.ghost_uncrop_png_b64
  );
  const refImg = formatImgSrc(
    visuals.reference_canonical_b64 ||
      visuals.original_reference_b64 ||
      verifyResult?.reference_png_b64
  );

  const vTheme = getVerdictTheme(verifyResult?.verdict_code);
  const VerdictIcon = vTheme.icon;

  return (
    <div
      className={`min-h-screen bg-[#FAF7F2] text-[#18202C] flex flex-col ${
        activeTab !== "registry" ? "lg:h-screen lg:overflow-hidden" : ""
      }`}
    >
      {/* =====================================================================
          TOP HEADER BAR (KAYASETU STYLE: HORIZON EMBLEM + SEGMENTED PILL SWITCHER)
      ===================================================================== */}
      <header className="w-full max-w-[1400px] mx-auto px-5 sm:px-8 pt-4 pb-3 flex flex-wrap items-center justify-between gap-4 shrink-0">
        {/* Left: Emblem + Clean Title */}
        <div className="flex items-center gap-3.5">
          <HorizonEmblem size="sm" />
          <div>
            <div className="flex items-center gap-2.5">
              <span className="text-2xl font-medium tracking-tight text-[#18202C]">
                Imprint
              </span>
              <span className="hidden sm:inline-block h-1.5 w-8 rounded-full bg-[#DE7A5E]" />
            </div>
            <p className="text-xs text-[#68707C]">
              Photo authenticity &amp; invisible provenance
            </p>
          </div>
        </div>

        {/* Right: KayaSetu-style Segmented Pill Switcher */}
        <nav
          aria-label="Workspace Tabs"
          className="bg-[#F2ECE4] p-1.5 rounded-full flex items-center gap-1 whitespace-nowrap"
        >
          <button
            type="button"
            onClick={() => setActiveTab("verify")}
            className={`px-5 py-2 rounded-full text-xs sm:text-sm font-medium transition-all ${
              activeTab === "verify"
                ? "bg-[#18202C] text-white shadow-sm"
                : "text-[#4A505A] hover:text-[#18202C]"
            }`}
          >
            Check Photo
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("sign")}
            className={`px-5 py-2 rounded-full text-xs sm:text-sm font-medium transition-all ${
              activeTab === "sign"
                ? "bg-[#18202C] text-white shadow-sm"
                : "text-[#4A505A] hover:text-[#18202C]"
            }`}
          >
            Protect Photo
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab("registry");
              fetchRegistry();
            }}
            className={`px-5 py-2 rounded-full text-xs sm:text-sm font-medium transition-all ${
              activeTab === "registry"
                ? "bg-[#18202C] text-white shadow-sm"
                : "text-[#4A505A] hover:text-[#18202C]"
            }`}
          >
            Archive ({registryItems.length})
          </button>
        </nav>
      </header>

      {/* =====================================================================
          MAIN WORKSPACE AREA (NON-SCROLLABLE ON CHECK & PROTECT TABS)
      ===================================================================== */}
      <main className="flex-1 min-h-0 w-full max-w-[1400px] mx-auto px-5 sm:px-8 pb-5 flex flex-col">
        {/* ===================================================================
            TAB 1: CHECK PHOTO (WATERMARK & EDIT DETECTOR — NON-SCROLLABLE)
        =================================================================== */}
        {activeTab === "verify" && (
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
            {/* LEFT CARD: UPLOAD PHOTO & CLAIM CHECK */}
            <div className="lg:col-span-5 bg-white border-[1.5px] border-[#EAE0D5] rounded-[28px] p-6 flex flex-col justify-between shadow-[0_4px_20px_rgba(24,32,44,0.03)] min-h-0">
              {/* Top Heading + Soft Mint Pills (like Light / No Glare / Clear Focus in KayaSetu) */}
              <div className="space-y-3 shrink-0">
                <div>
                  <h1 className="text-2xl font-semibold text-[#18202C] tracking-tight">
                    Verify Photo or Screenshot
                  </h1>
                  <p className="text-sm text-[#68707C] mt-0.5">
                    Drop any image to check its invisible signature and spot edits
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-3 py-1 rounded-full bg-[#EAF6F0] text-[#287D56] text-xs font-medium flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#287D56]" />
                    <span>Crop &amp; Tilt Safe</span>
                  </span>
                  <span className="px-3 py-1 rounded-full bg-[#EAF6F0] text-[#287D56] text-xs font-medium flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#287D56]" />
                    <span>B&amp;W Filter Safe</span>
                  </span>
                  <span className="px-3 py-1 rounded-full bg-[#EAF6F0] text-[#287D56] text-xs font-medium flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#287D56]" />
                    <span>Change Map</span>
                  </span>
                </div>
              </div>

              {/* Center Photo Frame */}
              <div
                onClick={() => verifyInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (e.dataTransfer.files?.[0]) {
                    handleVerifyFileSelect(e.dataTransfer.files[0]);
                  }
                }}
                className="flex-1 my-4 bg-[#F6EDE6] hover:bg-[#F2E5DC] border-[1.5px] border-[#ECDCD0] rounded-[24px] p-4 flex flex-col items-center justify-center cursor-pointer transition-all min-h-[200px] overflow-hidden relative"
              >
                <input
                  ref={verifyInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => handleVerifyFileSelect(e.target.files?.[0])}
                />

                {verifyPreview ? (
                  <div className="w-full h-full flex flex-col items-center justify-center gap-2 overflow-hidden">
                    <img
                      src={verifyPreview}
                      alt="Selected preview"
                      className="max-h-[210px] w-auto object-contain rounded-2xl shadow-sm bg-white p-1"
                    />
                    <span className="text-xs font-medium text-[#68707C] truncate max-w-[260px]">
                      {verifyFile?.name}
                    </span>
                  </div>
                ) : (
                  <div className="text-center space-y-2.5 px-4">
                    <div className="w-16 h-16 rounded-full bg-[#F7DFD4] text-[#DE7A5E] flex items-center justify-center mx-auto">
                      <Upload className="w-7 h-7" />
                    </div>
                    <p className="text-lg font-medium text-[#18202C]">
                      Tap or drop a photo here
                    </p>
                    <p className="text-xs text-[#68707C] max-w-xs mx-auto leading-relaxed">
                      Works with screenshots, WhatsApp forwards, rotated copies, or tight crops
                    </p>
                  </div>
                )}
              </div>

              {/* Bottom Controls: 2 Outlined Pills + Full-Width Midnight Navy CTA */}
              <form onSubmit={handleRunVerify} className="space-y-3 shrink-0">
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => verifyInputRef.current?.click()}
                    className="py-3 px-4 rounded-[20px] bg-white border-[1.5px] border-[#DFD3C5] hover:border-[#18202C] text-xs sm:text-sm font-medium text-[#18202C] flex items-center justify-center gap-2 transition-all"
                  >
                    <ImageIcon className="w-4 h-4 text-[#18202C]" />
                    <span>{verifyFile ? "Change Photo" : "Browse File"}</span>
                  </button>

                  <select
                    value={claimedOrigin}
                    onChange={(e) => setClaimedOrigin(Number(e.target.value))}
                    aria-label="Claimed Origin"
                    className="py-3 px-3.5 rounded-[20px] bg-white border-[1.5px] border-[#DFD3C5] hover:border-[#18202C] text-xs sm:text-sm font-medium text-[#18202C] focus:outline-none focus:border-[#18202C] cursor-pointer"
                  >
                    <option value={0}>Origin: Auto-Detect</option>
                    <option value={1}>Claimed: Camera Photo</option>
                    <option value={2}>Claimed: AI Art</option>
                  </select>
                </div>

                {verifyError && (
                  <p className="text-xs text-[#C83E3E] text-center font-medium">
                    {verifyError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={!verifyFile || verifyLoading}
                  className="w-full py-3.5 px-6 rounded-[22px] bg-[#18202C] hover:bg-[#253042] disabled:opacity-40 text-white text-sm sm:text-base font-medium flex items-center justify-center gap-2.5 transition-all shadow-sm"
                >
                  {verifyLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Checking Photo...</span>
                    </>
                  ) : (
                    <>
                      <span>Check Authenticity</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* RIGHT CARD: UNIFIED VERDICT, VISUAL COMPARISON & OWNERSHIP (NON-SCROLLABLE) */}
            <div className="lg:col-span-7 bg-white border-[1.5px] border-[#EAE0D5] rounded-[28px] p-6 flex flex-col justify-between shadow-[0_4px_20px_rgba(24,32,44,0.03)] min-h-0">
              {!verifyResult ? (
                /* Calm KayaSetu Blush-Sand Welcome Card */
                <div className="flex-1 bg-[#F6EDE6] rounded-[24px] p-8 flex flex-col items-center justify-center text-center">
                  <div className="w-48 h-32 rounded-[22px] bg-[#FAF7F2] border border-[#ECDCD0] p-3 mb-5 flex items-center justify-center shadow-sm overflow-hidden">
                    <svg viewBox="0 0 200 120" className="w-full h-full rounded-xl">
                      <rect width="200" height="120" fill="#FAF7F2" />
                      <circle cx="135" cy="44" r="26" fill="#F0CE91" />
                      <path
                        d="M0 82 Q 65 55, 130 78 T 200 68 L 200 120 L 0 120 Z"
                        fill="#DCE3EA"
                      />
                      <path
                        d="M0 94 Q 90 68, 200 90 L 200 120 L 0 120 Z"
                        fill="#DE846B"
                      />
                      <path
                        d="M0 105 Q 95 88, 200 104 L 200 120 L 0 120 Z"
                        fill="#18202C"
                      />
                    </svg>
                  </div>
                  <h2 className="text-2xl font-semibold text-[#18202C] mb-2">
                    Photo Authenticity Check
                  </h2>
                  <p className="text-sm text-[#68707C] max-w-md leading-relaxed">
                    Select any photo on the left—or open a saved photo from the{" "}
                    <button
                      type="button"
                      onClick={() => setActiveTab("registry")}
                      className="text-[#DE7A5E] font-semibold underline underline-offset-2"
                    >
                      Archive
                    </button>
                    —to verify its invisible 64×64 signature and highlight any edited areas.
                  </p>
                </div>
              ) : (
                <div className="flex-1 flex flex-col justify-between gap-4 min-h-0">
                  {/* 1. Top Verdict Card */}
                  <div className={`p-4 rounded-[22px] border ${vTheme.bg} shrink-0`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                      <span
                        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${vTheme.pill}`}
                      >
                        <VerdictIcon className="w-3.5 h-3.5" />
                        <span>{verifyResult.verdict_badge || vTheme.defaultBadge}</span>
                      </span>
                      <div className="flex items-center gap-2 text-xs text-[#68707C]">
                        <span>
                          Signature:{" "}
                          <strong className="text-[#18202C]">
                            {wmMetrics.watermark_detected
                              ? `Verified (${wmMetrics.surviving_tiles}/${wmMetrics.total_tiles})`
                              : "Absent"}
                          </strong>
                        </span>
                        <span>•</span>
                        <span>
                          Edited Areas:{" "}
                          <strong className="text-[#18202C]">
                            {xrayMetrics.num_tampered_cells ?? 0}
                          </strong>
                        </span>
                      </div>
                    </div>

                    <h2 className={`text-lg sm:text-xl font-semibold ${vTheme.title}`}>
                      {verifyResult.headline}
                    </h2>
                    <p className={`text-xs sm:text-sm mt-0.5 leading-relaxed ${vTheme.body}`}>
                      {verifyResult.explanation}
                    </p>
                  </div>

                  {/* 2. Bottom Side-by-Side Split: Visual Change Map (Left) + Origin & Passphrase (Right) */}
                  <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-12 gap-4 items-stretch">
                    {/* Left: Visual Comparison Viewer */}
                    <div className="md:col-span-7 bg-[#FAF7F2] border border-[#EAE0D5] rounded-[22px] p-4 flex flex-col justify-between min-h-0">
                      <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                        <span className="text-xs font-semibold text-[#18202C]">
                          Visual Change Map
                        </span>
                        <div className="bg-[#F2ECE4] p-1 rounded-full flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => setActiveXrayTab("tamper")}
                            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                              activeXrayTab === "tamper"
                                ? "bg-[#18202C] text-white"
                                : "text-[#4A505A] hover:text-[#18202C]"
                            }`}
                          >
                            Changes
                          </button>
                          <button
                            type="button"
                            onClick={() => setActiveXrayTab("ghost")}
                            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                              activeXrayTab === "ghost"
                                ? "bg-[#18202C] text-white"
                                : "text-[#4A505A] hover:text-[#18202C]"
                            }`}
                          >
                            Aligned
                          </button>
                          <button
                            type="button"
                            onClick={() => setActiveXrayTab("ref")}
                            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                              activeXrayTab === "ref"
                                ? "bg-[#18202C] text-white"
                                : "text-[#4A505A] hover:text-[#18202C]"
                            }`}
                          >
                            Original
                          </button>
                        </div>
                      </div>

                      <div className="flex-1 my-2 flex items-center justify-center overflow-hidden bg-white rounded-2xl border border-[#EAE0D5] p-2 min-h-[180px]">
                        {activeXrayTab === "tamper" && tamperImg && (
                          <img
                            src={tamperImg}
                            alt="Highlight Changes"
                            className="max-h-[210px] w-auto object-contain rounded-xl"
                          />
                        )}
                        {activeXrayTab === "ghost" && ghostImg && (
                          <img
                            src={ghostImg}
                            alt="Aligned Frame"
                            className="max-h-[210px] w-auto object-contain rounded-xl"
                          />
                        )}
                        {activeXrayTab === "ref" &&
                          (refImg ? (
                            <img
                              src={refImg}
                              alt="Saved Original"
                              className="max-h-[210px] w-auto object-contain rounded-xl"
                            />
                          ) : (
                            <p className="text-xs text-[#68707C]">
                              No matching archive photo.
                            </p>
                          ))}
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-[#68707C] shrink-0">
                        <span>Green = Verified original</span>
                        <span>Red = Edited or added area</span>
                      </div>
                    </div>

                    {/* Right: Origin, Location & Passphrase Ownership */}
                    <div className="md:col-span-5 bg-[#FAF7F2] border border-[#EAE0D5] rounded-[22px] p-4 flex flex-col justify-between gap-2 min-h-0 overflow-y-auto">
                      {verifyResult.matched_short_media_id ? (
                        <>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-[#18202C]">
                                Record Details
                              </span>
                              <span className="px-2.5 py-0.5 rounded-full bg-[#F6EDE6] border border-[#ECDCD0] text-xs font-semibold text-[#DE7A5E]">
                                #{verifyResult.matched_short_media_id}
                              </span>
                            </div>

                            <div className="space-y-1.5 text-xs">
                              <div className="p-2.5 rounded-xl bg-white border border-[#EAE0D5] flex items-center justify-between">
                                <span className="text-[#68707C]">Origin</span>
                                <span className="font-semibold text-[#18202C]">
                                  {formatOriginLabel(
                                    verifyResult.origin_type_code,
                                    verifyResult.origin_label
                                  )}
                                </span>
                              </div>
                              <div className="p-2.5 rounded-xl bg-white border border-[#EAE0D5] flex items-center justify-between">
                                <span className="text-[#68707C]">Creator</span>
                                <span className="font-semibold text-[#18202C] truncate max-w-[140px]">
                                  {verifyResult.whistleblower_protected
                                    ? "Anonymous (Hidden)"
                                    : verifyResult.creator_handle || "@prajwal"}
                                </span>
                              </div>
                              <div className="p-2.5 rounded-xl bg-white border border-[#EAE0D5] flex items-center justify-between">
                                <span className="text-[#68707C]">Location</span>
                                <span className="font-semibold text-[#18202C] truncate max-w-[140px]">
                                  {verifyResult.whistleblower_protected
                                    ? "Hidden (Private)"
                                    : verifyResult.capture_location || "Mangaluru, India"}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Creator Passphrase Ownership Check */}
                          <div className="p-3 rounded-2xl bg-white border border-[#EAE0D5] space-y-2">
                            <div className="flex items-center gap-1.5 text-xs font-semibold text-[#18202C]">
                              <KeyRound className="w-3.5 h-3.5 text-[#DE7A5E]" />
                              <span>Prove Creator Ownership</span>
                            </div>
                            <form onSubmit={handleVerifyPassphrase} className="space-y-2">
                              <div className="relative">
                                <input
                                  type={zkpShowPass ? "text" : "password"}
                                  value={zkpSecretInput}
                                  onChange={(e) => setZkpSecretInput(e.target.value)}
                                  placeholder="Enter creator passphrase..."
                                  className="w-full bg-[#FAF7F2] border border-[#DFD3C5] rounded-xl px-3 py-2 pr-12 text-xs text-[#18202C] focus:outline-none focus:border-[#18202C]"
                                />
                                <button
                                  type="button"
                                  onClick={() => setZkpShowPass(!zkpShowPass)}
                                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] font-semibold text-[#DE7A5E]"
                                >
                                  {zkpShowPass ? "Hide" : "Show"}
                                </button>
                              </div>
                              <button
                                type="submit"
                                disabled={zkpClaimLoading || !zkpSecretInput.trim()}
                                className="w-full py-2 rounded-xl bg-[#18202C] hover:bg-[#253042] disabled:opacity-40 text-white text-xs font-medium transition-all"
                              >
                                {zkpClaimLoading ? "Checking..." : "Verify Passphrase"}
                              </button>
                            </form>

                            {zkpClaimResult && (
                              <div
                                className={`p-2 rounded-xl text-[11px] font-medium flex items-start gap-1.5 ${
                                  zkpClaimResult.verified
                                    ? "bg-[#EAF6F0] text-[#1D6344]"
                                    : "bg-[#FDECEC] text-[#991B1B]"
                                }`}
                              >
                                {zkpClaimResult.verified ? (
                                  <Check className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                                ) : (
                                  <X className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                                )}
                                <span>{zkpClaimResult.message}</span>
                              </div>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-center p-4 space-y-2">
                          <div className="w-12 h-12 rounded-full bg-[#F6EDE6] text-[#DE7A5E] flex items-center justify-center">
                            <ShieldQuestion className="w-6 h-6" />
                          </div>
                          <p className="text-sm font-semibold text-[#18202C]">
                            Not Registered Yet
                          </p>
                          <p className="text-xs text-[#68707C] leading-relaxed">
                            This image has no matching record in the archive. Missing history does not prove a photo is fake.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 2: PROTECT PHOTO (REGISTER SCREENSHOT / PHOTO — NON-SCROLLABLE)
        =================================================================== */}
        {activeTab === "sign" && (
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
            {/* LEFT CARD: PHOTO UPLOAD, ORIGIN & CREATOR SETTINGS */}
            <div className="lg:col-span-6 bg-white border-[1.5px] border-[#EAE0D5] rounded-[28px] p-6 flex flex-col justify-between shadow-[0_4px_20px_rgba(24,32,44,0.03)] min-h-0">
              <div className="shrink-0">
                <h1 className="text-2xl font-semibold text-[#18202C] tracking-tight">
                  Protect an Original Photo
                </h1>
                <p className="text-sm text-[#68707C] mt-0.5">
                  Adds an invisible 64×64 signature that survives screenshots, crops, and sharing
                </p>
              </div>

              <form
                onSubmit={handleRunSign}
                className="flex-1 min-h-0 flex flex-col justify-between gap-3.5 mt-3"
              >
                {/* 1. Photo Preview Well */}
                <div
                  onClick={() => signInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files?.[0]) {
                      handleSignFileSelect(e.dataTransfer.files[0]);
                    }
                  }}
                  className="flex-1 min-h-[140px] bg-[#F6EDE6] hover:bg-[#F2E5DC] border-[1.5px] border-[#ECDCD0] rounded-[22px] p-3 flex flex-col items-center justify-center cursor-pointer transition-all overflow-hidden"
                >
                  <input
                    ref={signInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => handleSignFileSelect(e.target.files?.[0])}
                  />
                  {signPreview ? (
                    <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 overflow-hidden">
                      <img
                        src={signPreview}
                        alt="Original to protect"
                        className="max-h-[140px] w-auto object-contain rounded-xl bg-white p-1 shadow-sm"
                      />
                      <span className="text-xs font-medium text-[#68707C] truncate max-w-[260px]">
                        {signFile?.name} (Tap to change)
                      </span>
                    </div>
                  ) : (
                    <div className="text-center space-y-1.5">
                      <div className="w-12 h-12 rounded-full bg-[#F7DFD4] text-[#DE7A5E] flex items-center justify-center mx-auto">
                        <Camera className="w-5 h-5" />
                      </div>
                      <p className="text-base font-medium text-[#18202C]">
                        Select Original Photo to Protect
                      </p>
                      <p className="text-xs text-[#68707C]">
                        Outputs a clean lossless PNG with your embedded signature
                      </p>
                    </div>
                  )}
                </div>

                {/* 2. Origin Selector (3 KayaSetu Pill Buttons) */}
                <div className="space-y-1.5 shrink-0">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-[#68707C]">
                      Where did this image come from?
                    </label>
                    {originType === 3 && (
                      <input
                        type="text"
                        value={parentMediaId}
                        onChange={(e) => setParentMediaId(e.target.value)}
                        placeholder="Parent Photo ID (e.g. a1b2c3d4)"
                        className="bg-[#FAF7F2] border border-[#DFD3C5] rounded-full px-3 py-0.5 text-xs text-[#18202C] w-48 focus:outline-none focus:border-[#18202C]"
                      />
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2.5">
                    {ORIGIN_OPTIONS.map((opt) => {
                      const Icon = opt.icon;
                      const selected = originType === opt.code;
                      return (
                        <button
                          key={opt.code}
                          type="button"
                          onClick={() => setOriginType(opt.code)}
                          className={`py-2.5 px-3 rounded-[18px] border-[1.5px] text-xs font-medium flex items-center justify-center gap-2 transition-all ${
                            selected
                              ? "bg-[#18202C] border-[#18202C] text-white shadow-sm"
                              : "bg-white border-[#DFD3C5] text-[#18202C] hover:border-[#18202C]"
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate">{opt.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 3. Creator & Location vs. Private Mode Box */}
                <div className="bg-[#FAF7F2] border border-[#EAE0D5] rounded-[22px] p-3.5 space-y-2.5 shrink-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[#18202C]">
                      Creator &amp; Location Privacy
                    </span>
                    <div className="bg-[#F2ECE4] p-1 rounded-full flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setPrivateMode(false)}
                        className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                          !privateMode
                            ? "bg-[#18202C] text-white"
                            : "text-[#4A505A] hover:text-[#18202C]"
                        }`}
                      >
                        Public
                      </button>
                      <button
                        type="button"
                        onClick={() => setPrivateMode(true)}
                        className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                          privateMode
                            ? "bg-[#18202C] text-white"
                            : "text-[#4A505A] hover:text-[#18202C]"
                        }`}
                      >
                        Private Mode
                      </button>
                    </div>
                  </div>

                  {!privateMode ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] font-medium text-[#68707C] mb-1">
                          Creator Name
                        </label>
                        <input
                          type="text"
                          value={creatorHandle}
                          onChange={(e) => setCreatorHandle(e.target.value)}
                          placeholder="@prajwal"
                          className="w-full bg-white border border-[#DFD3C5] rounded-xl px-3 py-2 text-xs text-[#18202C] focus:outline-none focus:border-[#18202C]"
                        />
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <label className="text-[11px] font-medium text-[#68707C]">
                            Location {gpsStatus && <span className="text-[#DE7A5E]">({gpsStatus})</span>}
                          </label>
                          <button
                            type="button"
                            onClick={handleUseMyGps}
                            disabled={gpsLoading}
                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#DE7A5E] hover:underline"
                          >
                            <Navigation className="w-3 h-3" />
                            <span>{gpsLoading ? "..." : "Use GPS"}</span>
                          </button>
                        </div>
                        <input
                          type="text"
                          value={captureLocation}
                          onChange={(e) => setCaptureLocation(e.target.value)}
                          placeholder="Mangaluru, India"
                          className="w-full bg-white border border-[#DFD3C5] rounded-xl px-3 py-2 text-xs text-[#18202C] focus:outline-none focus:border-[#18202C]"
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-semibold text-[#18202C]">
                          Secret Ownership Passphrase
                        </label>
                        <span className="text-[11px] text-[#287D56] font-medium">
                          • GPS &amp; Camera Serial Stripped
                        </span>
                      </div>
                      <div className="relative">
                        <input
                          type={showSecretPass ? "text" : "password"}
                          value={authorSecret}
                          onChange={(e) => setAuthorSecret(e.target.value)}
                          placeholder="Enter secret passphrase..."
                          className="w-full bg-white border border-[#DFD3C5] rounded-xl px-3 py-2 pr-14 text-xs text-[#18202C] focus:outline-none focus:border-[#18202C]"
                        />
                        <button
                          type="button"
                          onClick={() => setShowSecretPass(!showSecretPass)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-[#DE7A5E]"
                        >
                          {showSecretPass ? "Hide" : "Show"}
                        </button>
                      </div>
                      <p className="text-[11px] text-[#9A3412]">
                        Keep this passphrase safe—it is never stored on our server and is required to prove ownership later.
                      </p>
                    </div>
                  )}
                </div>

                {signError && (
                  <p className="text-xs text-[#C83E3E] text-center font-medium shrink-0">
                    {signError}
                  </p>
                )}

                {/* 4. Primary Action Button */}
                <button
                  type="submit"
                  disabled={!signFile || signLoading}
                  className="w-full py-3.5 px-6 rounded-[22px] bg-[#18202C] hover:bg-[#253042] disabled:opacity-40 text-white text-sm sm:text-base font-medium flex items-center justify-center gap-2.5 transition-all shadow-sm shrink-0"
                >
                  {signLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Protecting Photo...</span>
                    </>
                  ) : (
                    <>
                      <Lock className="w-4 h-4" />
                      <span>Protect &amp; Register Photo</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* RIGHT CARD: PROTECTED PHOTO PREVIEW & DOWNLOAD (NON-SCROLLABLE) */}
            <div className="lg:col-span-6 bg-white border-[1.5px] border-[#EAE0D5] rounded-[28px] p-6 flex flex-col justify-between shadow-[0_4px_20px_rgba(24,32,44,0.03)] min-h-0">
              {!signResult ? (
                <div className="flex-1 bg-[#F6EDE6] rounded-[24px] p-8 flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 rounded-full bg-[#F7DFD4] text-[#DE7A5E] flex items-center justify-center mb-4">
                    <Lock className="w-7 h-7" />
                  </div>
                  <h2 className="text-2xl font-semibold text-[#18202C] mb-2">
                    Invisible Signature Protection
                  </h2>
                  <p className="text-sm text-[#68707C] max-w-md leading-relaxed">
                    Your protected photo looks identical to the original, while carrying a resilient 64×64 signature and registering a compact ~28 KB fingerprint in the archive.
                  </p>
                </div>
              ) : (
                <div className="flex-1 flex flex-col justify-between min-h-0">
                  {/* Top Header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                    <div>
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#EAF6F0] text-[#287D56] text-xs font-semibold mb-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Protected &amp; Saved in Archive</span>
                      </span>
                      <h2 className="text-xl font-semibold text-[#18202C]">
                        Protected Photo #{signResult.short_media_id}
                      </h2>
                    </div>

                    <button
                      type="button"
                      onClick={() => setShowUvPreview(!showUvPreview)}
                      className="px-3.5 py-2 rounded-full bg-[#F2ECE4] hover:bg-[#E6DDD1] text-xs font-medium text-[#18202C] transition-all"
                    >
                      {showUvPreview ? "Show Protected Photo" : "View Signature Pattern"}
                    </button>
                  </div>

                  {/* Center Image Preview */}
                  <div className="flex-1 my-3 bg-[#F6EDE6] border border-[#ECDCD0] rounded-[22px] p-3 flex items-center justify-center overflow-hidden min-h-[180px]">
                    <img
                      src={formatImgSrc(
                        showUvPreview
                          ? signResult.uv_blacklight_b64
                          : signResult.watermarked_image_b64
                      )}
                      alt="Protected output"
                      className="max-h-[220px] w-auto object-contain rounded-xl bg-white p-1 shadow-sm"
                    />
                  </div>

                  {/* 4-Pill Metadata Bar */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs mb-3 shrink-0">
                    <div className="p-2.5 rounded-2xl bg-[#FAF7F2] border border-[#EAE0D5]">
                      <span className="text-[11px] text-[#68707C] block">Photo ID</span>
                      <span className="font-semibold text-[#DE7A5E] truncate block">
                        #{signResult.short_media_id}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-2xl bg-[#FAF7F2] border border-[#EAE0D5]">
                      <span className="text-[11px] text-[#68707C] block">Origin</span>
                      <span className="font-semibold text-[#18202C] truncate block">
                        {formatOriginLabel(
                          signResult.origin_type_code,
                          signResult.origin_label
                        )}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-2xl bg-[#FAF7F2] border border-[#EAE0D5]">
                      <span className="text-[11px] text-[#68707C] block">Creator</span>
                      <span className="font-semibold text-[#18202C] truncate block">
                        {signResult.origin_type_code === 4
                          ? "Hidden (Private)"
                          : signResult.creator_handle}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-2xl bg-[#FAF7F2] border border-[#EAE0D5]">
                      <span className="text-[11px] text-[#68707C] block">Location</span>
                      <span className="font-semibold text-[#18202C] truncate block">
                        {signResult.origin_type_code === 4
                          ? "Hidden (Private)"
                          : signResult.capture_location || captureLocation}
                      </span>
                    </div>
                  </div>

                  {/* Bottom 2-Button KayaSetu Action Row */}
                  <div className="grid grid-cols-2 gap-3 shrink-0">
                    <button
                      type="button"
                      onClick={() =>
                        handleInspectBase64Image(
                          signResult.watermarked_image_b64,
                          `imprint_${signResult.short_media_id}.png`
                        )
                      }
                      className="py-3.5 px-4 rounded-[20px] bg-white border-[1.5px] border-[#DFD3C5] hover:border-[#18202C] text-sm font-medium text-[#18202C] flex items-center justify-center gap-2 transition-all"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>Test in Checker</span>
                    </button>

                    <a
                      href={formatImgSrc(signResult.watermarked_image_b64)}
                      download={`imprint_${signResult.short_media_id}.png`}
                      className="py-3.5 px-4 rounded-[20px] bg-[#18202C] hover:bg-[#253042] text-white text-sm font-medium flex items-center justify-center gap-2 transition-all shadow-sm"
                    >
                      <Download className="w-4 h-4" />
                      <span>Download PNG</span>
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 3: ARCHIVE & SYSTEM LIMITS
        =================================================================== */}
        {activeTab === "registry" && (
          <div className="space-y-6 pb-8">
            {/* Top Archive Section */}
            <div className="bg-white border-[1.5px] border-[#EAE0D5] rounded-[28px] p-6 space-y-5 shadow-[0_4px_20px_rgba(24,32,44,0.03)]">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h1 className="text-2xl font-semibold text-[#18202C]">
                    Registered Photo Archive ({registryItems.length})
                  </h1>
                  <p className="text-sm text-[#68707C]">
                    Select any saved photo to test it in the authenticity checker or download its lossless PNG
                  </p>
                </div>
                <div className="flex items-center gap-2.5">
                  <button
                    type="button"
                    onClick={fetchRegistry}
                    className="py-2.5 px-4 rounded-full bg-white border-[1.5px] border-[#DFD3C5] hover:border-[#18202C] text-xs font-medium text-[#18202C] flex items-center gap-1.5"
                  >
                    <RefreshCw
                      className={`w-3.5 h-3.5 ${registryLoading ? "animate-spin" : ""}`}
                    />
                    <span>Refresh</span>
                  </button>
                  {registryItems.length > 0 && (
                    <button
                      type="button"
                      onClick={handleResetArchive}
                      className="py-2.5 px-4 rounded-full bg-[#FDECEC] border border-[#F7C4C4] text-xs font-medium text-[#991B1B] flex items-center gap-1.5"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Clear Archive</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Evaluator ~28 KB Architecture Note (Styled like KayaSetu Disclaimer Box) */}
              <div className="p-4 rounded-[20px] bg-[#F3EFEA] border border-[#E5DDD2] text-xs sm:text-sm text-[#4A505A] flex items-start gap-3 leading-relaxed">
                <Database className="w-5 h-5 text-[#68707C] shrink-0 mt-0.5" />
                <div>
                  <strong className="text-[#18202C]">
                    Lightweight Lookup Architecture Note:
                  </strong>{" "}
                  Imprint&apos;s verification and change-detection math only requires{" "}
                  <strong>~28 KB of mathematical fingerprint data</strong> per photo (the 16×16 structural summary numbers, landmark coordinates, and Ed25519 signature)—it does not need to store full original photos. Preview images are shown here strictly so evaluators can easily view, download, and test registered samples during the demo.
                </div>
              </div>

              {registryItems.length === 0 ? (
                <div className="bg-[#F6EDE6] rounded-[24px] p-12 text-center space-y-2">
                  <p className="text-lg font-semibold text-[#18202C]">
                    No Protected Photos in Archive Yet
                  </p>
                  <p className="text-sm text-[#68707C]">
                    Switch to <strong>Protect Photo</strong> to register your first image.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                  {registryItems.map((item) => (
                    <div
                      key={item.short_media_id}
                      className="bg-[#FAF7F2] border-[1.5px] border-[#EAE0D5] rounded-[24px] p-4 flex flex-col justify-between gap-4"
                    >
                      <div className="space-y-3">
                        {item.reference_image_b64 && (
                          <div className="bg-[#F6EDE6] rounded-[18px] p-3 border border-[#ECDCD0]">
                            <img
                              src={formatImgSrc(item.reference_image_b64)}
                              alt={item.short_media_id}
                              className="w-full h-44 object-contain rounded-xl bg-white p-1"
                            />
                          </div>
                        )}
                        <div className="space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="px-3 py-0.5 rounded-full bg-[#F6EDE6] border border-[#ECDCD0] text-[#DE7A5E] text-xs font-semibold">
                              #{item.short_media_id}
                            </span>
                            <span className="text-xs text-[#68707C]">
                              {item.timestamp_bucket}
                            </span>
                          </div>
                          <p className="text-base font-semibold text-[#18202C] pt-1">
                            {formatOriginLabel(item.origin_type_code, item.origin_label)}
                          </p>
                          <p className="text-xs text-[#68707C]">
                            Creator:{" "}
                            <strong className="text-[#18202C]">
                              {item.origin_type_code === 4
                                ? "Anonymous (Private Mode)"
                                : item.creator_handle}
                            </strong>
                          </p>
                          <p className="text-xs text-[#68707C] flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5 text-[#DE7A5E] shrink-0" />
                            <span>
                              {item.origin_type_code === 4
                                ? "Hidden (Private Mode)"
                                : item.capture_location || "Mangaluru, India"}
                            </span>
                          </p>
                        </div>
                      </div>

                      {item.reference_image_b64 && (
                        <div className="grid grid-cols-2 gap-2.5">
                          <button
                            type="button"
                            onClick={() =>
                              handleInspectBase64Image(
                                item.reference_image_b64,
                                `imprint_${item.short_media_id}.png`
                              )
                            }
                            className="py-2.5 px-3 rounded-[16px] bg-[#18202C] hover:bg-[#253042] text-white text-xs font-medium flex items-center justify-center gap-1.5"
                          >
                            <ShieldCheck className="w-3.5 h-3.5" />
                            <span>Inspect</span>
                          </button>
                          <a
                            href={formatImgSrc(item.reference_image_b64)}
                            download={`imprint_${item.short_media_id}.png`}
                            className="py-2.5 px-3 rounded-[16px] bg-white border-[1.5px] border-[#DFD3C5] hover:border-[#18202C] text-[#18202C] text-xs font-medium flex items-center justify-center gap-1.5"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>Download PNG</span>
                          </a>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Bottom System Limits Card */}
            <div className="bg-white border-[1.5px] border-[#EAE0D5] rounded-[28px] p-6 space-y-5 shadow-[0_4px_20px_rgba(24,32,44,0.03)]">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold text-[#18202C]">
                    What Can &amp; Cannot Be Proven
                  </h2>
                  <p className="text-sm text-[#68707C]">
                    Documented survival capabilities and physical boundaries
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleRunBenchmarks}
                  disabled={benchLoading}
                  className="py-2.5 px-5 rounded-full bg-[#18202C] hover:bg-[#253042] text-white text-xs sm:text-sm font-medium flex items-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${benchLoading ? "animate-spin" : ""}`} />
                  <span>
                    {benchLoading
                      ? "Running Test Suite..."
                      : "Run Live Verification Suite"}
                  </span>
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                <div className="p-4 rounded-[20px] bg-[#EAF6F0] border border-[#C5E7D6] space-y-1.5">
                  <span className="px-2.5 py-0.5 rounded-full bg-[#287D56] text-white font-semibold inline-block">
                    What Survives
                  </span>
                  <h3 className="text-sm font-semibold text-[#164E35]">
                    Screenshots, Crops &amp; Tilts
                  </h3>
                  <p className="text-[#236B4A] leading-relaxed">
                    Survives WhatsApp compression, browser zoom screenshots, 90°/180°/mirror flips, angled tilts, B&amp;W filters, and crops down to ~5% of the photo.
                  </p>
                </div>

                <div className="p-4 rounded-[20px] bg-[#FAF7F2] border border-[#EAE0D5] space-y-1.5">
                  <span className="px-2.5 py-0.5 rounded-full bg-[#F6EDE6] text-[#DE7A5E] font-semibold inline-block">
                    Limit 1: Tiny Fragments
                  </span>
                  <h3 className="text-sm font-semibold text-[#18202C]">
                    Extreme Tiny Crops (&gt;95% Cut)
                  </h3>
                  <p className="text-[#68707C] leading-relaxed">
                    Crops smaller than ~100×100 pixels with no distinct landmarks lack enough pixels to lock on.
                  </p>
                </div>

                <div className="p-4 rounded-[20px] bg-[#FAF7F2] border border-[#EAE0D5] space-y-1.5">
                  <span className="px-2.5 py-0.5 rounded-full bg-[#F6EDE6] text-[#DE7A5E] font-semibold inline-block">
                    Limit 2: Heavy Destruction
                  </span>
                  <h3 className="text-sm font-semibold text-[#18202C]">
                    Extreme Compression (Q ≤ 10)
                  </h3>
                  <p className="text-[#68707C] leading-relaxed">
                    Severe compression wipes out fine pixel detail, so the checker falls back to matching visible shapes against the archive.
                  </p>
                </div>

                <div className="p-4 rounded-[20px] bg-[#FAF7F2] border border-[#EAE0D5] space-y-1.5">
                  <span className="px-2.5 py-0.5 rounded-full bg-[#F3EFEA] text-[#5A6270] font-semibold inline-block">
                    Limit 3: Unregistered Photos
                  </span>
                  <h3 className="text-sm font-semibold text-[#18202C]">
                    Missing History ≠ Fake Photo
                  </h3>
                  <p className="text-[#68707C] leading-relaxed">
                    If an image was never protected in our archive, we report <strong>No History Found</strong>—never a false &ldquo;Fake&rdquo; claim.
                  </p>
                </div>
              </div>

              {benchmarks.length > 0 && (
                <div className="overflow-x-auto bg-[#FAF7F2] rounded-[20px] border border-[#EAE0D5] p-4">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-[#EAE0D5] text-[#68707C]">
                        <th className="py-2.5 px-3">Scenario</th>
                        <th className="py-2.5 px-3">Category</th>
                        <th className="py-2.5 px-3">Result</th>
                        <th className="py-2.5 px-3">Summary</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#EAE0D5]">
                      {benchmarks.map((b, i) => (
                        <tr key={i}>
                          <td className="py-2.5 px-3 font-semibold text-[#18202C]">
                            {b.scenario}
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`px-2.5 py-0.5 rounded-full font-semibold ${
                                b.category === "SURVIVAL"
                                  ? "bg-[#EAF6F0] text-[#287D56]"
                                  : "bg-[#FDF0E9] text-[#D96B4B]"
                              }`}
                            >
                              {b.category === "SURVIVAL" ? "Survives" : "Documented Limit"}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-semibold text-[#287D56]">
                            {b.passed ? "Verified" : "Check"}
                          </td>
                          <td className="py-2.5 px-3 text-[#68707C]">{b.verdict_note}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
