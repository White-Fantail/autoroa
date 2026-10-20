import { useEffect, useRef, useState } from "react";
import { CameraView, useCameraPermissions } from "expo-camera";
import { router, useLocalSearchParams } from "expo-router";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import type { Vehicle } from "../../../packages/types/src";
import { createLocalCapture, saveCapturePhoto, syncLocalCaptures, type CaptureMode } from "../lib/capture-queue";

export default function QuickCapture() {
  const params = useLocalSearchParams<{ mode?: string }>();
  const mode: CaptureMode = params.mode === "full" ? "full" : "receipt";
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView | null>(null);
  const [vehicle, setVehicle] = useState<Vehicle>();
  const [phase, setPhase] = useState<"receipt" | "odometer" | "done">("receipt");
  const [key, setKey] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  useEffect(() => {
    let active = true;
    api.get<Vehicle[]>("/vehicles").then(items => {
      if (!active) return;
      const selected = items.find(item => item.is_primary && !item.is_archived) ??
        items.find(item => !item.is_archived);
      setVehicle(selected);
      if (!selected) setError("Add a vehicle before scanning a receipt.");
    }).catch(() => { if (active) setError("Could not load your vehicle. Check your connection."); });
    return () => { active = false; };
  }, []);

  async function capture() {
    if (!vehicle || busy || !cameraRef.current) return;
    setBusy(true);
    setError(undefined);
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.8, skipProcessing: false });
      if (!photo?.uri) throw new Error("Could not capture the photo.");
      if (phase === "receipt") {
        const entry = await createLocalCapture(vehicle.id, mode);
        await saveCapturePhoto(entry.clientKey, "receipt", photo.uri);
        setKey(entry.clientKey);
        void syncLocalCaptures();
        setPhase(mode === "full" ? "odometer" : "done");
      } else if (phase === "odometer" && key) {
        await saveCapturePhoto(key, "odometer", photo.uri);
        void syncLocalCaptures();
        setPhase("done");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Photo could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  if (!permission) return <View style={styles.center}><ActivityIndicator /></View>;
  if (!permission.granted) return (
    <View style={styles.center}>
      <Text style={styles.title}>Camera access is needed to scan a receipt.</Text>
      <Pressable style={styles.button} onPress={() => void requestPermission()}>
        <Text style={styles.actionText}>Allow camera</Text>
      </Pressable>
    </View>
  );
  if (phase === "done") return (
    <View style={styles.center}>
      <Text style={styles.symbol}>✓</Text>
      <Text style={styles.title}>Photo saved</Text>
      <Text style={styles.subtitle}>You can leave now. Upload and recognition will continue when available.</Text>
      <Pressable onPress={() => router.replace("/(tabs)")} style={styles.button}>
        <Text style={styles.actionText}>Home</Text>
      </Pressable>
    </View>
  );
  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" />
      <View style={styles.header}>
        <Text style={styles.title}>{phase === "receipt" ? "Scan fuel receipt" : "Scan odometer"}</Text>
        <Text style={styles.subtitle}>
          {phase === "receipt" ? "One photo is all you need." : "Optional — receipt already saved."}
        </Text>
        {vehicle && <Text style={styles.subtitle}>{vehicle.nickname}</Text>}
      </View>
      <View style={styles.bottom}>
        {error && <Text style={styles.error}>{error}</Text>}
        <Pressable accessibilityRole="button" accessibilityLabel="Capture photo" disabled={!vehicle || busy}
          style={[styles.shutter, (!vehicle || busy) && styles.disabled]} onPress={() => void capture()}>
          {busy ? <ActivityIndicator /> : <View style={styles.shutterInner} />}
        </Pressable>
        {phase === "odometer" && (
          <Pressable onPress={() => setPhase("done")}><Text style={styles.actionText}>Skip odometer</Text></Pressable>
        )}
        <Pressable onPress={() => router.replace("/(tabs)")}><Text style={styles.subtitle}>Cancel</Text></Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: "#122921", padding: 28, gap: 18 },
  header: { marginTop: 55, padding: 22, backgroundColor: "rgba(0,0,0,0.5)", gap: 7 },
  title: { color: "white", fontSize: 24, fontWeight: "700", textAlign: "center" },
  subtitle: { color: "#d8e8e0", fontSize: 14, textAlign: "center" },
  bottom: { position: "absolute", bottom: 42, width: "100%", gap: 20, alignItems: "center" },
  shutter: { width: 78, height: 78, borderRadius: 39, borderWidth: 5, borderColor: "#fff", justifyContent: "center", alignItems: "center" },
  shutterInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: "white" },
  disabled: { opacity: 0.35 },
  button: { backgroundColor: "#26664e", borderRadius: 14, paddingHorizontal: 28, paddingVertical: 16 },
  actionText: { color: "white", fontWeight: "600", fontSize: 16 },
  symbol: { color: "#67dda8", fontSize: 70, fontWeight: "700" },
  error: { color: "#ffb0a5", fontWeight: "600", textAlign: "center", backgroundColor: "#4b1721", padding: 12 }
});
