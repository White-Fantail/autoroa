import { useEffect, useRef, useState } from "react";
import { CameraView, useCameraPermissions } from "expo-camera";
import { router, useLocalSearchParams } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import { getStoredItem, setStoredItem } from "../lib/storage";
import {
  finishReceiptOnly, saveOdometerLocally, saveReceiptLocally, syncQuickCaptures,
  type CaptureMode,
} from "../lib/capture-queue";
import type { Vehicle } from "../../../packages/types/src";

export default function QuickCaptureScreen() {
  const params = useLocalSearchParams<{mode?:string}>();
  const mode: CaptureMode = params.mode === "full" ? "full" : "receipt";
  const camera = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [vehicleId, setVehicleId] = useState<string>();
  const [token, setToken] = useState<string>();
  const [step, setStep] = useState<"receipt"|"odometer">("receipt");
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    async function loadVehicle() {
      const userId=await getStoredItem("autoroa_user_id");
      const key=userId?`autoroa_primary_vehicle:${userId}`:null;
      const cached=key?await getStoredItem(key):null;
      if(active&&cached)setVehicleId(cached);
      try {
        const rows=await api.get<Vehicle[]>("/vehicles");
        if(!active)return;
        const chosen=rows.find(item=>item.is_primary)??rows[0];
        if(!chosen){router.replace("/onboarding/vehicle");return;}
        setVehicleId(chosen.id);
        if(key)await setStoredItem(key,chosen.id);
      } catch {
        if(active&&!cached)setError("Connect once to set up your vehicle before offline capture.");
      }
    }
    void loadVehicle();
    return () => { active = false; };
  }, []);

  async function capture() {
    if (busy || !ready || !vehicleId) return;
    setBusy(true);
    setError(undefined);
    try {
      const picture = await camera.current?.takePictureAsync({ quality: 0.85, skipProcessing: false });
      if (!picture?.uri) throw new Error("The camera did not return a picture");
      if (step === "receipt") {
        const id = await saveReceiptLocally(picture.uri, vehicleId, mode);
        setToken(id);
        if (mode === "full") {
          setStep("odometer");
        } else {
          void syncQuickCaptures();
          router.replace("/");
        }
      } else {
        if (!token) throw new Error("The receipt capture could not be found");
        await saveOdometerLocally(token, picture.uri);
        void syncQuickCaptures();
        router.replace("/");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the photo");
    } finally {
      setBusy(false);
    }
  }

  async function skipOdometer() {
    if (!token || busy) return;
    setBusy(true);
    try {
      await finishReceiptOnly(token);
      void syncQuickCaptures();
      router.replace("/");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not finish capture");
      setBusy(false);
    }
  }

  if (!permission) return <View style={styles.fallback}><Text>Preparing camera…</Text></View>;
  if (!permission.granted) return (
    <View style={styles.fallback}>
      <Text style={styles.intro}>Camera access lets Autoroa save your fuel receipt in one shot.</Text>
      <Pressable style={styles.permission} onPress={() => void requestPermission()}>
        <Text style={styles.permissionText}>Allow camera</Text>
      </Pressable>
      <Pressable onPress={() => router.back()}><Text>Cancel</Text></Pressable>
    </View>
  );

  return (
    <View style={styles.screen}>
      <CameraView style={StyleSheet.absoluteFill} facing="back" ref={camera}
        onCameraReady={() => setReady(true)} />
      <View style={styles.header}>
        <Text style={styles.heading}>{step === "receipt" ? "Receipt" : "Odometer"}</Text>
        <Text style={styles.subheading}>{step === "receipt" ? "Frame the entire fuel receipt" : "Capture the total kilometres, not the trip meter"}</Text>
      </View>
      <View style={styles.bottom}>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <View style={styles.actions}>
          <Pressable accessibilityRole="button" onPress={() => router.back()}>
            <Text style={styles.cancel}>Close</Text>
          </Pressable>
          <Pressable accessibilityLabel="Take photo" accessibilityRole="button"
            disabled={!ready || !vehicleId || busy} onPress={() => void capture()}
            style={[styles.shutter, (!ready || !vehicleId || busy) && styles.disabled]}>
            <View style={styles.innerShutter} />
          </Pressable>
          {step === "odometer" ? (
            <Pressable accessibilityRole="button" onPress={() => void skipOdometer()}>
              <Text style={styles.cancel}>Skip</Text>
            </Pressable>
          ) : <Text style={styles.caption}>{mode === "full" ? "1 / 2" : "1 / 1"}</Text>}
        </View>
        <Text style={styles.footnote}>
          {step === "receipt"
            ? "Saved securely on this phone before syncing"
            : "Your receipt is already saved"}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen:{flex:1,backgroundColor:"#10231E"},
  fallback:{flex:1,justifyContent:"center",alignItems:"center",gap:20,padding:30},
  intro:{fontSize:18,textAlign:"center"},
  permission:{backgroundColor:"#175D4D",padding:16,borderRadius:12},
  permissionText:{color:"white",fontWeight:"700"},
  header:{marginTop:74,marginHorizontal:22,padding:16,backgroundColor:"rgba(0,0,0,0.45)",borderRadius:14},
  heading:{fontSize:23,fontWeight:"700",color:"#fff",textAlign:"center"},
  subheading:{fontSize:14,color:"#fff",textAlign:"center",marginTop:6},
  bottom:{position:"absolute",left:0,right:0,bottom:0,paddingBottom:46,paddingTop:20,backgroundColor:"rgba(0,0,0,0.45)",alignItems:"center"},
  actions:{flexDirection:"row",width:"100%",alignItems:"center",justifyContent:"space-evenly"},
  cancel:{color:"#fff",fontSize:16,minWidth:54,textAlign:"center"},
  caption:{color:"#fff",fontSize:15,minWidth:54,textAlign:"center"},
  shutter:{height:78,width:78,borderRadius:39,borderColor:"#fff",borderWidth:4,alignItems:"center",justifyContent:"center"},
  innerShutter:{backgroundColor:"#fff",height:64,width:64,borderRadius:32},
  disabled:{opacity:.45},
  footnote:{color:"#E3F0EA",fontSize:12,marginTop:15},
  error:{color:"#FFB8B0",textAlign:"center",marginBottom:12,paddingHorizontal:20},
});
