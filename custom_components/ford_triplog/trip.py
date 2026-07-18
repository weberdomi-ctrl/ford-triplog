"""
Ford Triplog

Trip model.

Version: 1.2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BATTERY_CAPACITY_KWH = 77.0

class Trip:
    def __init__(self, **data):
        self.schema=data.get("schema",1)
        self.trip_id=data.get("trip_id")
        self.created=data.get("created")
        self.start_time=data.get("start_time")
        self.end_time=data.get("end_time")
        self.start_odometer=data.get("start_odometer")
        self.end_odometer=data.get("end_odometer")
        self.start_soc=data.get("start_soc")
        self.end_soc=data.get("end_soc")
        self.soc_used=data.get("soc_used")
        self.start_latitude=data.get("start_latitude")
        self.start_longitude=data.get("start_longitude")
        self.end_latitude=data.get("end_latitude")
        self.end_longitude=data.get("end_longitude")
        self.start_address=data.get("start_address")
        self.end_address=data.get("end_address")
        self.distance_km=data.get("distance_km")
        self.duration_seconds=data.get("duration_seconds")
        self.average_speed_kmh=data.get("average_speed_kmh")
        self.energy_used_kwh=data.get("energy_used_kwh")
        self.consumption_kwh_100km=data.get("consumption_kwh_100km")
        self.notes=data.get("notes")
        self.tags=data.get("tags",[])

    def start(self, odometer=None, soc=None, latitude=None, longitude=None, address=None):
        now=datetime.now(timezone.utc)
        self.trip_id=now.strftime("%Y%m%dT%H%M%S")
        self.created=now.isoformat().replace("+00:00","Z")
        self.start_time=now.isoformat()
        self.start_odometer=float(odometer) if odometer not in (None,"","unknown") else None
        self.start_soc=float(soc) if soc not in (None,"","unknown") else None
        self.start_latitude=latitude
        self.start_longitude=longitude
        self.start_address=address

    def finish(self, odometer=None, soc=None, latitude=None, longitude=None, address=None):
        now=datetime.now(timezone.utc)
        self.end_time=now.isoformat()
        self.end_odometer=float(odometer) if odometer not in (None,"","unknown") else None
        self.end_soc=float(soc) if soc not in (None,"","unknown") else None
        self.end_latitude=latitude
        self.end_longitude=longitude
        self.end_address=address
        self._calculate_values()

    def _calculate_values(self):
        if self.start_time and self.end_time:
            s=datetime.fromisoformat(self.start_time.replace("Z","+00:00"))
            e=datetime.fromisoformat(self.end_time.replace("Z","+00:00"))
            self.duration_seconds=int((e-s).total_seconds())
        if self.start_odometer is not None and self.end_odometer is not None:
            self.distance_km=round(self.end_odometer-self.start_odometer,1)
        if self.distance_km and self.duration_seconds:
            h=self.duration_seconds/3600
            if h>0:
                self.average_speed_kmh=round(self.distance_km/h,1)
        if self.start_soc is not None and self.end_soc is not None:
            self.soc_used=round(self.start_soc-self.end_soc,1)
            self.energy_used_kwh=round(self.soc_used*BATTERY_CAPACITY_KWH/100,2)
            if self.distance_km and self.distance_km>0:
                self.consumption_kwh_100km=round(self.energy_used_kwh/self.distance_km*100,1)

    def to_dict(self)->dict[str,Any]:
        return {
            "schema":self.schema,
            "trip_id":self.trip_id,
            "created":self.created,
            "start_time":self.start_time,
            "end_time":self.end_time,
            "start_odometer":self.start_odometer,
            "end_odometer":self.end_odometer,
            "start_soc":self.start_soc,
            "end_soc":self.end_soc,
            "soc_used":self.soc_used,
            "start_latitude":self.start_latitude,
            "start_longitude":self.start_longitude,
            "end_latitude":self.end_latitude,
            "end_longitude":self.end_longitude,
            "start_address":self.start_address,
            "end_address":self.end_address,
            "distance_km":self.distance_km,
            "duration_seconds":self.duration_seconds,
            "average_speed_kmh":self.average_speed_kmh,
            "energy_used_kwh":self.energy_used_kwh,
            "consumption_kwh_100km":self.consumption_kwh_100km,
            "notes":self.notes,
            "tags":self.tags,
            "generator":"Ford Triplog",
            "version":"1.0.0"
        }

    @classmethod
    def from_dict(cls,data):
        return cls(**data)
