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

def extract_vehicle_registration_fields(text:str)->dict[str,str]:
    """Conservative CH/DE registration parser; all results remain user-reviewable."""
    t=' '.join((text or '').replace('\r','\n').split())
    out:dict[str,str]={}
    pats={
      'vin':[r'(?:Fahrgestell(?:nummer|-Nr\.?|nr\.?|nummer)?|FIN|VIN|Identifizierungsnummer)\s*[:\-]?\s*([A-HJ-NPR-Z0-9]{17})'],
      'registration_number':[r'(?:Kontrollschild|Kennzeichen|Amtliches Kennzeichen)\s*[:\-]?\s*([A-ZÄÖÜ]{1,3}[ -]?[A-Z0-9 -]{2,10})'],
      'first_registration':[r'(?:1\.?\s*Inverkehrsetzung|Erstzulassung|Datum der ersten Zulassung)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})'],
      'make':[r'(?:Marke|Hersteller)\s*[:\-]?\s*([A-Za-z0-9ÄÖÜäöü .\-]{2,30})'],
      'type_approval':[r'(?:Typengenehmigung|Typgenehmigung|Typenschein)\s*[:\-]?\s*([A-Za-z0-9.\-]+)'],
      'power_kw':[r'(?:Leistung|Nennleistung)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*kW'],
      'empty_weight_kg':[r'(?:Leergewicht|Masse des in Betrieb befindlichen Fahrzeugs)\s*[:\-]?\s*(\d{3,5})\s*kg'],
      'gross_weight_kg':[r'(?:Gesamtgewicht|zulässige Gesamtmasse)\s*[:\-]?\s*(\d{3,5})\s*kg'],
    }
    for k,arr in pats.items():
        for p in arr:
            m=re.search(p,t,re.I)
            if m: out[k]=m.group(1).strip(); break
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
