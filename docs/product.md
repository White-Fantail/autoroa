# Product decisions

Autoroa's primary value exchange is: queue receipt and odometer scans, confirm uncertain fields, receive accurate spend/economy history, and contribute minimal pseudonymous price evidence. Private provenance remains internally linked for audit and deletion but is never included in public price responses. High-confidence OCR results (≥.90) are applied automatically only when their destination is already known; medium (.70–.899), attention-required (<.70), and unassigned station price-board results require explicit confirmation.

Admin station pricing offers two independent actions: upload a photo into the background OCR queue, or enter prices manually for immediate application. Admins may also upload a price-board photo without selecting a station. The queue then requires station selection and price review before applying it.

Economy is only computed between valid full tanks. Partial-fill litres/cost are accumulated; missed fills, non-increasing odometers, or unreliable chains yield `null`. Pump price is the comparable public value; loyalty paid price remains separate. Freshness states are Very fresh (<1h), Fresh (1–6h), Recent (6–24h), Old (1–3d), and Stale (>3d).

The MVP covers account/vehicle/fill-up workflows, discovery and personal metrics, plus operational review. Reminders, EV charging, rewards, marketplace, subscriptions, navigation, and fleet functionality remain extension points.
