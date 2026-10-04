"""Vehicle master data and document storage for Ford Triplog."""
from __future__ import annotations
import functools, mimetypes, re, shutil, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from .const import STORAGE_DIR

_ALLOWED={'.pdf','.jpg','.jpeg','.png','.webp'}

class FordTriplogVehicleDocumentStorage:
    def __init__(self,hass:HomeAssistant)->None:
        self.hass=hass; self.directory=Path(hass.config.path('.storage',STORAGE_DIR,'vehicle_documents'))
    async def async_setup(self)->None:
        await self.hass.async_add_executor_job(self.directory.mkdir,0o755,True,True)
    async def async_import(self,source_path:str|Path,original_name:str|None=None)->dict[str,Any]:
        await self.async_setup(); source=Path(source_path); supplied=Path(original_name or source.name).name
        suffix=Path(supplied).suffix.lower() or source.suffix.lower()
        if suffix not in _ALLOWED: raise ValueError('Unsupported vehicle document type')
        content=await self.hass.async_add_executor_job(source.read_bytes)
        if not content: raise ValueError('Vehicle document is empty')
        name=f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:12]}{suffix}"
        await self.hass.async_add_executor_job(functools.partial(shutil.copyfile,source,self.directory/name))
        return {'filename':name,'original_filename':supplied,'media_type':mimetypes.guess_type(supplied)[0] or 'application/octet-stream','content':content}
    async def async_get_details(self,vehicle_id:int)->dict[str,Any]|None:
        from .database import FordTriplogDatabase
        db=FordTriplogDatabase(self.hass,Path(self.hass.config.path('.storage',STORAGE_DIR))); await db.async_setup()
        def _r():
            with sqlite3.connect(db.db_path) as c:
                c.row_factory=sqlite3.Row; row=c.execute('SELECT * FROM vehicle_details WHERE vehicle_id=?',(int(vehicle_id),)).fetchone(); return dict(row) if row else None
        return await self.hass.async_add_executor_job(_r)
    async def async_save_details(self,vehicle_id:int,data:dict[str,Any])->None:
        from .database import FordTriplogDatabase
        db=FordTriplogDatabase(self.hass,Path(self.hass.config.path('.storage',STORAGE_DIR))); await db.async_setup(); now=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        fields=['vin','registration_number','make','model','first_registration','type_approval','empty_weight_kg','gross_weight_kg','power_kw','registration_document_filename','registration_document_original_name']
        vals=[data.get(x) or None for x in fields]
        def _w():
            with sqlite3.connect(db.db_path) as c:
                exists=c.execute('SELECT 1 FROM vehicle_details WHERE vehicle_id=?',(int(vehicle_id),)).fetchone()
                if exists:
                    c.execute('UPDATE vehicle_details SET '+','.join(f'{x}=?' for x in fields)+',updated_at=? WHERE vehicle_id=?',(*vals,now,int(vehicle_id)))
                else:
                    c.execute('INSERT INTO vehicle_details (vehicle_id,'+','.join(fields)+',created_at,updated_at) VALUES ('+','.join('?' for _ in range(len(fields)+3))+')',(int(vehicle_id),*vals,now,now))
                c.commit()
        await self.hass.async_add_executor_job(_w)
    async def async_attach(self,vehicle_id:int,filename:str,original_filename:str,media_type:str|None,document_type:str,note:str|None)->int:
        from .database import FordTriplogDatabase
        db=FordTriplogDatabase(self.hass,Path(self.hass.config.path('.storage',STORAGE_DIR))); await db.async_setup()
        def _w():
            with sqlite3.connect(db.db_path) as c:
                cur=c.execute('INSERT INTO vehicle_documents (vehicle_id,filename,original_filename,media_type,document_type,note,created_at) VALUES (?,?,?,?,?,?,?)',(int(vehicle_id),filename,original_filename,media_type,document_type,note,time.strftime('%Y-%m-%dT%H:%M:%S%z'))); c.commit(); return int(cur.lastrowid)
        return await self.hass.async_add_executor_job(_w)
    async def async_list(self,vehicle_id:int)->list[dict[str,Any]]:
        from .database import FordTriplogDatabase
        db=FordTriplogDatabase(self.hass,Path(self.hass.config.path('.storage',STORAGE_DIR))); await db.async_setup()
        def _r():
            with sqlite3.connect(db.db_path) as c:
                c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute('SELECT * FROM vehicle_documents WHERE vehicle_id=? ORDER BY created_at,document_id',(int(vehicle_id),)).fetchall()]
        return await self.hass.async_add_executor_job(_r)
    async def async_get_document(self,vehicle_id:int,document_id:int)->dict[str,Any]|None:
        items=await self.async_list(vehicle_id); return next((x for x in items if int(x['document_id'])==int(document_id)),None)
    async def async_delete(self,vehicle_id:int,document_id:int)->None:
        from .database import FordTriplogDatabase
        db=FordTriplogDatabase(self.hass,Path(self.hass.config.path('.storage',STORAGE_DIR))); await db.async_setup()
        def _d():
            with sqlite3.connect(db.db_path) as c:
                row=c.execute('SELECT filename FROM vehicle_documents WHERE vehicle_id=? AND document_id=?',(int(vehicle_id),int(document_id))).fetchone()
                if not row:return None
                c.execute('DELETE FROM vehicle_documents WHERE vehicle_id=? AND document_id=?',(int(vehicle_id),int(document_id))); c.commit(); return row[0]
        fn=await self.hass.async_add_executor_job(_d)
        if fn: await self.hass.async_add_executor_job((self.directory/Path(fn).name).unlink,True)
    def get_path(self,filename:str|None)->Path|None:
        if not filename:return None
        p=self.directory/Path(filename).name
        try:p.resolve().relative_to(self.directory.resolve())
        except ValueError:return None
        return p


def render_vehicle_registration_png(content: bytes, page_number: int = 0) -> bytes:
    """Render and optimise a scanned registration document for OCR.

    Registration scans often contain large white scanner margins.  Rendering at
    higher resolution, cropping those margins and applying autocontrast gives
    the OCR service substantially more useful pixels without changing the
    stored original document.
    """
    from io import BytesIO
    import fitz
    from PIL import Image, ImageChops, ImageEnhance, ImageOps

    document = fitz.open(stream=content, filetype="pdf")
    try:
        if document.page_count <= page_number:
            return b""
        page = document.load_page(page_number)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(3.5, 3.5), alpha=False)
        raw = pixmap.tobytes("png")
    finally:
        document.close()

    image = Image.open(BytesIO(raw)).convert("RGB")
    # Find everything that differs sufficiently from a white scanner page.
    gray = ImageOps.grayscale(image)
    mask = ImageChops.invert(gray).point(lambda value: 255 if value > 18 else 0)
    bbox = mask.getbbox()
    if bbox:
        pad = max(20, int(min(image.size) * 0.015))
        left = max(0, bbox[0] - pad); top = max(0, bbox[1] - pad)
        right = min(image.width, bbox[2] + pad); bottom = min(image.height, bbox[3] + pad)
        image = image.crop((left, top, right, bottom))
    image = ImageOps.autocontrast(image, cutoff=0.5)
    image = ImageEnhance.Contrast(image).enhance(1.15)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()

def extract_vehicle_registration_fields(text: str, expected_vin: str | None = None) -> dict[str, str]:
    """Extract CH/DE registration fields from OCR text for user review."""
    raw = (text or "").replace("\r", "\n")
    t = " ".join(raw.split())
    out: dict[str, str] = {}

    def first(patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, t, re.I)
            if match:
                return match.group(1).strip(" :;,-")
        return None

    # Swiss registration documents are multilingual and OCR frequently inserts
    # spaces into VINs and dotted Stammnummern.  Keep parsing conservative: all
    # values are still shown to the user before they are saved.
    vin = first([
        r"(?:Fahrgestell(?:nummer|-Nr\.?|nr\.?|nummer)?|Chassis|VIN|FIN|Identifizierungsnummer)\s*[:\-]?\s*((?:[A-HJ-NPR-Z0-9][ \t.-]*){17,22})",
    ])
    if vin:
        candidate = re.sub(r"[^A-HJ-NPR-Z0-9]", "", vin.upper())
        if len(candidate) >= 17:
            out["vin"] = candidate[:17]

    # The selected Triplog vehicle already has a canonical VIN.  Scanned CH
    # documents often split the VIN into groups or OCR confuses individual
    # glyphs.  Prefer an exact occurrence after normalization; if OCR did not
    # produce a usable VIN at all, use the canonical VIN as a safe prefill for
    # this vehicle (the review form still requires user confirmation).
    canonical_vin = re.sub(r"[^A-HJ-NPR-Z0-9]", "", (expected_vin or "").upper())
    normalized_ocr = re.sub(r"[^A-HJ-NPR-Z0-9]", "", raw.upper())
    if len(canonical_vin) == 17:
        if canonical_vin in normalized_ocr or "vin" not in out:
            out["vin"] = canonical_vin

    value = first([
        r"(?:Kontrollschild|Schild|Plaque|Targa|Kennzeichen|Amtliches Kennzeichen)\s*[:\-]?\s*([A-Z]{1,3}\s*\d{2,6})",
    ])
    if value:
        out["registration_number"] = re.sub(r"\s+", " ", value.upper()).strip()

    value = first([
        r"(?:1\.?\s*Inverkehrsetzung|1\.?\s*Inverkehrssetzung|Inverkehrsetzung|1re mise en circulation|1a messa in circolazione|Erstzulassung|Datum der ersten Zulassung)[^0-9]{0,45}(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})",
    ])
    if not value:
        # Preserve OCR line structure: on Swiss forms the date can be printed
        # in the neighbouring line/cell rather than immediately after label.
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        for idx, line in enumerate(lines):
            if re.search(r"Inverkehr|Erstzulassung|mise en circulation|messa in circolazione", line, re.I):
                window = " ".join(lines[idx:idx + 3])
                match = re.search(r"(\d{1,2}[.\-/]\d{1,2}[.\-/](?:\d{2}|\d{4}))", window)
                if match:
                    value = match.group(1)
                    break
    if value: out["first_registration"] = value

    value = first([r"(?:Marke und Typ|Marque et type|Marca e tipo)\s*[:\-]?\s*([A-Z0-9][A-Z0-9 ._\-/]{2,40})"])
    if value:
        words=value.split()
        if words:
            out["make"]=words[0]
            if len(words)>1: out["model"]=" ".join(words[1:])
    else:
        value=first([r"(?:Marke|Hersteller)\s*[:\-]?\s*([A-Za-z0-9ÄÖÜäöü .\-]{2,30})"])
        if value: out["make"]=value

    value = first([r"(?:Typengenehmigung|Typgenehmigung|Approbation du type|Approvazione del tipo|Typenschein)\s*[:\-]?\s*([A-Z0-9 .\-]{3,20})"])
    if value: out["type_approval"] = re.sub(r"\s+", "", value)

    value = first([r"(?:Leistung|Puissance|Potenza|Nennleistung)\s*(?:kW)?\s*[:\-]?\s*\*{0,6}\s*(\d{2,4}(?:[.,]\d+)?)", r"(?:Leistung|Puissance|Potenza)[^0-9]{0,30}(\d{2,4}(?:[.,]\d+)?)\s*kW"])
    if value: out["power_kw"] = value.replace(",", ".")

    value = first([r"(?:Leergewicht|Poids à vide|Peso a vuoto)[^0-9]{0,25}\*{0,6}\s*(\d{3,5})"])
    if value: out["empty_weight_kg"] = value
    value = first([r"(?:Gesamtgewicht|Poids total|Peso totale|zulässige Gesamtmasse)[^0-9]{0,25}\*{0,6}\s*(\d{3,5})"])
    if value: out["gross_weight_kg"] = value

    return out

class FordTriplogVehicleDocumentView(HomeAssistantView):
    url='/api/ford_triplog/vehicle/{vehicle_id}/documents/{document_ref}'
    name='api:ford_triplog:vehicle_document'; requires_auth=True
    async def get(self,request:web.Request,vehicle_id:str,document_ref:str)->web.StreamResponse:
        hass=request.app['hass']; s=FordTriplogVehicleDocumentStorage(hass); await s.async_setup(); filename=original=media=None
        if document_ref=='registration':
            d=await s.async_get_details(int(vehicle_id))
            if d: filename=d.get('registration_document_filename'); original=d.get('registration_document_original_name')
        else:
            try:d=await s.async_get_document(int(vehicle_id),int(document_ref))
            except ValueError:d=None
            if d: filename=d.get('filename'); original=d.get('original_filename'); media=d.get('media_type')
        path=s.get_path(filename)
        if path is None or not await hass.async_add_executor_job(path.is_file): raise web.HTTPNotFound()
        resp=web.FileResponse(path); resp.headers['Content-Disposition']=f'inline; filename="{Path(original or path.name).name.replace(chr(34),"")}"'
        if media: resp.content_type=media
        return resp
