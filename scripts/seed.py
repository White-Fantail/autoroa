"""Create deterministic Christchurch development data without production-price claims."""
import sys, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"services/api"))
from app.db import Base, SessionLocal, engine
from app.models import Brand, Station
BRANDS=["NPD","Z","BP","Mobil","Caltex","Waitomo","Gull"]
LOCATIONS=[("Moorhouse",-43.5398,172.6326),("Riccarton",-43.5290,172.5985),("Papanui",-43.4955,172.6078),("Hornby",-43.5432,172.5278),("Ferrymead",-43.5582,172.7100),("Sydenham",-43.5517,172.6380),("Wigram",-43.5590,172.5550)]
Base.metadata.create_all(engine)
with SessionLocal() as db:
    for brand_name,(suburb,lat,lng) in zip(BRANDS,LOCATIONS):
        brand=Brand(id=uuid.uuid5(uuid.NAMESPACE_DNS,f"dev-{brand_name}"),name=brand_name,slug=brand_name.lower());db.merge(brand)
        db.merge(Station(id=uuid.uuid5(uuid.NAMESPACE_DNS,f"dev-{brand_name}-{suburb}"),brand_id=brand.id,name=f"{brand_name} {suburb}",address_line=f"Development address, {suburb}",suburb=suburb,city="Christchurch",region="Canterbury",latitude=lat,longitude=lng))
    db.commit()
print("Seeded development stations; no fuel prices were fabricated.")
