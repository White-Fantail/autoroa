import { useCallback, useState } from "react";
import { AppState, Pressable, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Card, s } from "./ui";
import { getPendingCaptures, syncQuickCaptures, type CaptureOutboxStatus } from "../lib/capture-queue";

export default function CaptureOutboxCard() {
  const [status, setStatus] = useState<CaptureOutboxStatus>({items:[],unreadableCount:0});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const refresh = useCallback(async () => {
    try {
      setStatus(await getPendingCaptures());
      setError(undefined);
    } catch {
      setError("Could not read the saved photo queue. Do not uninstall the app.");
    }
  }, []);

  useFocusEffect(useCallback(() => {
    let active = true;
    const refreshIfActive = () => { if(active) void refresh(); };
    const sub = AppState.addEventListener("change", state => {
      if(state === "active") refreshIfActive();
    });
    refreshIfActive();
    void syncQuickCaptures().then(refreshIfActive).catch(refreshIfActive);
    return () => { active = false; sub.remove(); };
  }, [refresh]));

  async function retry() {
    if(loading) return;
    setLoading(true);
    try {
      await syncQuickCaptures({force:true});
      await refresh();
    } catch {
      setError("Sync could not start. Your photos are still saved on this phone.");
    } finally {
      setLoading(false);
    }
  }

  if(!status.items.length && !status.unreadableCount && !error) return null;
  return <Card>
    <Text style={{fontWeight:"700",fontSize:17}}>Photos waiting to sync</Text>
    <Text style={s.muted}>Saved on this device. Uploading is separate from AI processing.</Text>
    {status.items.slice(0,6).map(item => (
      <View key={item.token} style={{paddingVertical:10,borderBottomWidth:1,borderColor:"#E5EFEB",gap:3}}>
        <Text style={{fontWeight:"600"}}>
          {item.mode === "full" ? "Receipt + odometer" : "Fuel receipt"} · {new Date(item.createdAt).toLocaleString("en-NZ")}
        </Text>
        <Text style={{color:item.lastError?"#9C4C19":"#587074"}}>
          {item.waitingForOdometer ? "Receipt saved · waiting for odometer" :
            item.lastError ? "Upload interrupted · photo kept safely" : "Waiting to upload"}
        </Text>
        {item.nextRetryAt && item.nextRetryAt > Date.now() &&
          <Text style={s.muted}>Retry on next app activity after {new Date(item.nextRetryAt).toLocaleTimeString("en-NZ")}</Text>}
      </View>
    ))}
    {status.items.length > 6 && <Text style={s.muted}>And {status.items.length - 6} more saved photos</Text>}
    {status.unreadableCount > 0 &&
      <Text style={s.danger}>{status.unreadableCount} local capture folder(s) need recovery. Keep the app installed.</Text>}
    {error && <Text accessibilityRole="alert" style={s.danger}>{error}</Text>}
    <Pressable accessibilityRole="button" disabled={loading} style={[s.button,{marginTop:8},loading&&s.disabled]} onPress={() => void retry()}>
      <Text style={s.buttonText}>{loading?"Checking connection…":"Retry uploads now"}</Text>
    </Pressable>
  </Card>;
}
