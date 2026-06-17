import os
import io
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
from dotenv import load_dotenv
from PIL import Image

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import anthropic

app = FastAPI(title="Cuneiform Translator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_client():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an expert cuneiformist and ancient Near Eastern linguist specializing in Sumerian and Akkadian. You translate ancient cuneiform texts with scholarly precision.

When given transliterated cuneiform text, you:
1. Identify the language (Sumerian, Akkadian, Hittite, Elamite, or other)
2. Identify the period/genre if discernible (e.g. Ur III administrative, Old Babylonian letter, Neo-Assyrian royal inscription)
3. Provide a clear English translation
4. Note any words or phrases that are damaged, uncertain, or have multiple interpretations — use [...] for damaged/missing text and (?) for uncertain readings
5. Add brief scholarly notes on anything historically or linguistically significant

Transliteration conventions:
- Sumerograms are in CAPITALS (e.g. LUGAL = king)
- Akkadian syllables are in lowercase (e.g. šar-rum = king)
- Determinatives appear in superscript notation (e.g. dEN.ZU = the god Nanna/Sin)
- Numbers may appear as digits
- Breaks or damage: [...] or x

Respond in this JSON format:
{
  "language": "Sumerian | Akkadian | Hittite | Unknown | Mixed",
  "period": "brief description or null",
  "genre": "administrative | legal | literary | royal | religious | letter | other",
  "translation": "the English translation",
  "notes": ["array of scholarly notes, each a string"],
  "confidence": "high | medium | low",
  "confidence_reason": "brief explanation of confidence level"
}"""


class TranslateRequest(BaseModel):
    text: str


class TranslateResponse(BaseModel):
    language: str
    period: str | None
    genre: str
    translation: str
    notes: list[str]
    confidence: str
    confidence_reason: str


@app.post("/api/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    if len(text) > 5000:
        raise HTTPException(status_code=400, detail="Text too long (max 5000 characters)")

    try:
        message = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Please translate this cuneiform text:\n\n{text}"
                }
            ]
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return TranslateResponse(**result)

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Model returned malformed response")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"API error: {str(e)}")


IMAGE_SYSTEM_PROMPT = """You are an expert cuneiformist and ancient Near Eastern linguist with decades of experience reading cuneiform tablets. You have been given a photograph of an ancient tablet or inscription.

Your task:
1. Examine the image carefully for cuneiform signs, inscriptions, or clay tablet markings
2. Attempt to read and transliterate any visible cuneiform signs line by line, using standard transliteration conventions:
   - Sumerograms in CAPITALS
   - Akkadian syllables in lowercase with diacritics where identifiable
   - Determinatives in curly braces e.g. {d} for divine, {ki} for place
   - Damaged or unclear signs as x or [...]
3. Identify the language, script period, and genre
4. Provide an English translation of what can be read
5. Note confidence level — image quality, damage, and viewing angle all affect readability

If the image does not appear to contain cuneiform or is too unclear to read, say so honestly.

Respond in this JSON format:
{
  "language": "Sumerian | Akkadian | Hittite | Unknown | Mixed | Not cuneiform",
  "period": "brief description or null",
  "genre": "administrative | legal | literary | royal | religious | letter | other | unknown",
  "transliteration": "your line-by-line transliteration of visible signs, or null if unreadable",
  "translation": "English translation of readable text, or description of what is visible",
  "notes": ["array of scholarly notes about the tablet, script, condition, etc."],
  "confidence": "high | medium | low",
  "confidence_reason": "explanation — image quality, damage, script clarity, etc."
}"""


class ImageTranslateResponse(BaseModel):
    language: str
    period: str | None
    genre: str
    transliteration: str | None
    translation: str
    notes: list[str]
    confidence: str
    confidence_reason: str


ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024   # 50 MB raw upload limit
MAX_LONG_EDGE = 2048                   # resize to fit within this
MAX_API_BYTES = 4 * 1024 * 1024        # Anthropic image limit


def prepare_image(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Resize image if needed and return (bytes, media_type) ready for the API."""
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Resize if either dimension exceeds MAX_LONG_EDGE
    if max(img.width, img.height) > MAX_LONG_EDGE:
        img.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.LANCZOS)

    # Re-encode as JPEG for consistent output
    buf = io.BytesIO()
    quality = 88
    img.save(buf, format="JPEG", quality=quality, optimize=True)

    # If still too large, drop quality until it fits
    while buf.tell() > MAX_API_BYTES and quality > 50:
        quality -= 10
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)

    return buf.getvalue(), "image/jpeg"


@app.post("/api/translate-image", response_model=ImageTranslateResponse)
async def translate_image(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use JPEG, PNG, or WebP.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 50 MB).")

    data, media_type = prepare_image(data, file.content_type)
    b64 = base64.standard_b64encode(data).decode("utf-8")

    try:
        message = get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1536,
            system=IMAGE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Please examine this tablet image and provide a transliteration and translation of any cuneiform text visible."
                        }
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return ImageTranslateResponse(**result)

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Model returned malformed response")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"API error: {str(e)}")


@app.get("/api/examples")
async def examples():
    return [
        {
            "label": "Ur III grain receipt",
            "text": "0.0.3 še gur\nmu-kux(DU)\nku-li\nsipa udu-ka\nitu ezem-{d}nin-a-zu\nmu us2-sa {d}amar-{d}EN.ZU lugal-e ur-bi2-lum{ki} mu-hul"
        },
        {
            "label": "Hammurabi law excerpt",
            "text": "šum-ma a-wi-lum\nī-in a-wi-lim\nuḫ-ta-ap-pi-id\nī-in-šu u-ḫa-ap-pa-du"
        },
        {
            "label": "Gilgamesh flood tablet excerpt",
            "text": "ul-tu u4-mi šu-a-tu\nu4-mi 6 u4-mi 7\na-bu-bu id-di-ma\nšá-ru-ú ra-aq-tu e-li māti il-lu-la"
        }
    ]


CDLI_BASE   = "https://cdli.earth/search?format=json"
CDLI_PHOTO  = "https://cdli.earth/dl/photo/{p}.jpg"
CDLI_HEADERS = {"User-Agent": "CuneiformTranslator/1.0 (research tool)"}


def _cdli_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=CDLI_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def _photo_url(artifact_id: int) -> str:
    return CDLI_PHOTO.format(p=f"P{artifact_id:06d}")


def _has_photo(artifact_id: int) -> bool:
    try:
        req = urllib.request.Request(_photo_url(artifact_id), headers=CDLI_HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _clean_artifact(a: dict) -> dict:
    period = a.get("period") or {}
    genres = [g.get("genre", {}).get("genre", "") for g in a.get("genres", []) if g.get("genre")]
    langs  = [l.get("language", {}).get("language", "") for l in a.get("languages", []) if l.get("language")]
    colls  = [c.get("collection", {}).get("collection", "") for c in a.get("collections", []) if c.get("collection")]
    art_id = a.get("id", 0)
    p_number = f"P{art_id:06d}"
    inscription = a.get("inscription") or {}
    atf = inscription.get("atf", "") if isinstance(inscription, dict) else ""
    return {
        "p_number":    p_number,
        "designation": a.get("designation", ""),
        "museum_no":   a.get("museum_no", "") or "",
        "period":      period.get("period", "") if period else "",
        "genres":      [g for g in genres if g],
        "languages":   [l for l in langs if l],
        "collections": [c for c in colls if c],
        "photo_url":   _photo_url(art_id),
        "atf":         atf,
    }


@app.get("/api/cdli/search")
async def cdli_search(
    period: str = Query(None),
    genre:  str = Query(None),
    p_number: str = Query(None),
    limit: int = Query(12, ge=1, le=50),
):
    # Direct P-number lookup
    if p_number:
        p = p_number.upper().strip()
        if not (p.startswith("P") and p[1:].isdigit()):
            raise HTTPException(status_code=400, detail="Invalid P-number (e.g. P106294)")
        try:
            raw = _cdli_get(f"https://cdli.earth/api/artifacts/{p}")
            artifact = json.loads(raw)
            return [_clean_artifact(artifact)]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise HTTPException(status_code=404, detail=f"{p} not found in CDLI")
            raise HTTPException(status_code=502, detail=f"CDLI error: {e}")
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=502, detail=f"CDLI unreachable: {e}")

    # Filter by period / genre
    params = f"&limit={limit}"
    if period:
        params += f"&period={urllib.parse.quote(period)}"
    if genre:
        params += f"&genre={urllib.parse.quote(genre)}"

    try:
        raw = _cdli_get(f"{CDLI_BASE}{params}")
        artifacts = json.loads(raw)
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"CDLI unreachable: {e}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="CDLI returned unexpected response")

    return [_clean_artifact(a) for a in artifacts]


@app.get("/api/cdli/filters")
async def cdli_filters():
    return {
        "periods": [
            "Uruk IV (ca. 3350-3200 BC)",
            "Uruk III (ca. 3200-3000 BC)",
            "Early Dynastic I-II (ca. 2900-2700 BC)",
            "Early Dynastic IIIa (ca. 2600-2500 BC)",
            "Early Dynastic IIIb (ca. 2500-2340 BC)",
            "Ebla (ca. 2350-2300 BC)",
            "Lagash II (ca. 2200-2100 BC)",
            "Ur III (ca. 2100-2000 BC)",
            "Old Babylonian (ca. 1900-1600 BC)",
            "Old Assyrian (ca. 1950-1850 BC)",
            "Middle Babylonian (ca. 1400-1100 BC)",
            "Middle Assyrian (ca. 1400-1000 BC)",
            "Neo-Assyrian (ca. 911-612 BC)",
            "Neo-Babylonian (ca. 626-539 BC)",
            "Achaemenid (547-331 BC)",
        ],
        "genres": [
            "Administrative",
            "Legal",
            "Letter",
            "Literary",
            "Lexical",
            "Mathematical",
            "Medical",
            "Astronomical",
            "Royal or monumental",
            "Ritual",
            "Votive",
        ],
    }


class CDLITranslateRequest(BaseModel):
    p_number: str
    atf_text: str | None = None


@app.post("/api/cdli/translate", response_model=ImageTranslateResponse)
async def cdli_translate(req: CDLITranslateRequest):
    p = req.p_number.upper().strip()
    if not p.startswith("P") or not p[1:].isdigit():
        raise HTTPException(status_code=400, detail="Invalid P-number format (e.g. P106294)")

    # ATF text path: faster, more accurate, uses Haiku
    if req.atf_text and len(req.atf_text.strip()) > 10:
        try:
            message = get_client().messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Translate this cuneiform text from CDLI ({p}). "
                        f"It is in ATF (Assyriological Text Format) — lines starting with &, #atf, or @ are "
                        f"structural markers; numbered lines are the inscription itself:\n\n{req.atf_text}"
                    )
                }],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw.strip())
            result["transliteration"] = req.atf_text
            return ImageTranslateResponse(**result)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Model returned malformed response")
        except anthropic.APIError as e:
            raise HTTPException(status_code=502, detail=f"API error: {str(e)}")

    # Photo fallback: download tablet image, use Sonnet vision
    photo_url = f"https://cdli.earth/dl/photo/{p}.jpg"
    try:
        data = _cdli_get(photo_url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(status_code=404, detail=f"No photo available for {p} in CDLI")
        raise HTTPException(status_code=502, detail=f"CDLI photo fetch failed: {e}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"CDLI unreachable: {e}")

    data, media_type = prepare_image(data, "image/jpeg")
    b64 = base64.standard_b64encode(data).decode("utf-8")

    try:
        message = get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1536,
            system=IMAGE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": f"Please examine this cuneiform tablet ({p} from the CDLI database) and provide a transliteration and translation of any visible text."}
                ],
            }],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return ImageTranslateResponse(**result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Model returned malformed response")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"API error: {str(e)}")


# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
