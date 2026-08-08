# Product decisions

Carfolio's primary value exchange is: scan receipt and odometer, confirm uncertain fields, receive accurate spend/economy history, and contribute minimal anonymous price evidence. The review step is never skipped. Confidence bands are high (≥.90), medium (.70–.899), and attention required (<.70).

Economy is only computed between valid full tanks. Partial-fill litres/cost are accumulated; missed fills, non-increasing odometers, or unreliable chains yield `null`. Pump price is the comparable public value; loyalty paid price remains separate. Freshness states are Very fresh (<1h), Fresh (1–6h), Recent (6–24h), Old (1–3d), and Stale (>3d).

The MVP covers account/vehicle/fill-up workflows, discovery and personal metrics, plus operational review. Reminders, EV charging, rewards, marketplace, subscriptions, navigation, and fleet functionality remain extension points.
