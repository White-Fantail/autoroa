import { useState } from "react";
import { Pressable, Text, TextInput } from "react-native";
import * as Location from "expo-location";
import { router } from "expo-router";
import { Button, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import type { FuelType } from "../../../../packages/types/src";
export default function VehicleOnboarding() {
  const [form, setForm] = useState({
    nickname: "",
    make: "",
    model: "",
    fuel_type: "PETROL_91" as FuelType,
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [permissionStep,setPermissionStep]=useState(false);
  async function save() {
    setSaving(true);
    setError("");
    try {
      await api.post("/vehicles", { ...form, is_primary: true });
      setPermissionStep(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create vehicle");
    } finally {
      setSaving(false);
    }
  }
  if(permissionStep)return <Screen title="Find nearby fuel"><Text>Location helps find nearby prices and match a receipt to a station. Carfolio only requests location while you use these features; you can continue without it.</Text><Button label="Allow location" onPress={async()=>{await Location.requestForegroundPermissionsAsync();router.replace('/(tabs)')}}/><Button label="Not now" onPress={()=>router.replace('/(tabs)')}/></Screen>;
  return (
    <Screen title="Add your car">
      <Text>Your vehicle keeps fill-ups and fuel economy separate.</Text>
      {(["nickname", "make", "model"] as const).map((key) => (
        <TextInput
          key={key}
          placeholder={key}
          value={form[key]}
          onChangeText={(value) => setForm((x) => ({ ...x, [key]: value }))}
        />
      ))}
      <Text>Fuel type</Text>{(['PETROL_91','PETROL_95','PETROL_98','DIESEL','OTHER'] as FuelType[]).map(fuel=><Pressable key={fuel} onPress={()=>setForm(x=>({...x,fuel_type:fuel}))}><Text>{fuel}{form.fuel_type===fuel?' · Selected':''}</Text></Pressable>)}
      <Button
        label={saving ? "Saving…" : "Create vehicle"}
        disabled={saving || !form.nickname || !form.make || !form.model}
        onPress={save}
      />
      {error && <Text accessibilityRole="alert">{error}</Text>}
    </Screen>
  );
}
