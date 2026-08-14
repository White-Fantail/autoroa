# Product decisions

Autoroa's primary value exchange is: queue receipt and odometer scans, confirm uncertain fields, receive accurate spend/economy history, and contribute minimal pseudonymous price evidence. Private provenance remains internally linked for audit and deletion but is never included in public price responses. High-confidence OCR results (≥.90) are applied automatically; medium (.70–.899) and attention-required (<.70) results require explicit confirmation.

Economy is only computed between valid full tanks. Partial-fill litres/cost are accumulated; missed fills, non-increasing odometers, or unreliable chains yield `null`. Pump price is the comparable public value; loyalty paid price remains separate. Freshness states are Very fresh (<1h), Fresh (1–6h), Recent (6–24h), Old (1–3d), and Stale (>3d).

The MVP covers account/vehicle/fill-up workflows, discovery and personal metrics, plus operational review. Reminders, EV charging, rewards, marketplace, subscriptions, navigation, and fleet functionality remain extension points.
