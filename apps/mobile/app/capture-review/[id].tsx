import { useEffect, useState } from "react";
import { router, useLocalSearchParams } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../../lib/api";
import { fuelTypes, formatLocalDateTime, localDateTimeToIso } from "../../lib/fill-up-form";
import type { FuelType } from "../../../../packages/types/src";

type Capture = {
  id:string; receipt_id:string; odometer_reading_id?:string|null;
  vehicle_id:string; status:string; error_code?:string|null;
};
type Receipt = {
  transaction_datetime?:string|null; fuel_type?:FuelType|null;
  litres?:string|null; pump_price_per_litre?:string|null;
  discount_amount?:string|null; total_amount?:string|null;
};
type Reading = {reading_km?:number|null};

export default function CaptureReviewScreen() {
  const {id} = useLocalSearchParams<{id:string}>();
  const [capture, setCapture] = useState<Capture>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const [time, setTime] = useState(formatLocalDateTime(new Date().toISOString()));
  const [fuelType, setFuelType] = useState<FuelType>("PETROL_91");
  const [litres, setLitres] = useState("");
  const [price, setPrice] = useState("");
  const [discount, setDiscount] = useState("0");
  const [total, setTotal] = useState("");
  const [odometer, setOdometer] = useState("");
  const [allowArithmetic, setAllowArithmetic] = useState(false);
  const [allowFuelMismatch, setAllowFuelMismatch] = useState(false);
  const [allowTankCapacity, setAllowTankCapacity] = useState(false);
  const [allowOdometerConflict, setAllowOdometerConflict] = useState(false);

  useEffect(() => {
    let active=true;
    async function load() {
      try {
        const item=await api.get<Capture>(`/quick-captures/${id}`);
        const receipt=await api.get<Receipt>(`/receipts/${item.receipt_id}`);
        const odo=item.odometer_reading_id
          ? await api.get<Reading>(`/odometer-readings/${item.odometer_reading_id}`)
          : null;
        if(!active)return;
        setCapture(item);
        if(receipt.transaction_datetime)setTime(formatLocalDateTime(receipt.transaction_datetime));
        if(receipt.fuel_type&&receipt.fuel_type!=="OTHER")setFuelType(receipt.fuel_type);
        setLitres(receipt.litres??"");
        setPrice(receipt.pump_price_per_litre??"");
        setDiscount(receipt.discount_amount??"0");
        setTotal(receipt.total_amount??"");
        if(odo?.reading_km!=null)setOdometer(String(odo.reading_km));
      } catch(caught) {
        if(active)setError(caught instanceof Error?caught.message:"Could not load this capture");
      } finally {
        if(active)setLoading(false);
      }
    }
    void load();
    return ()=>{active=false};
  }, [id]);

  async function confirm() {
    if(!capture||saving)return;
    const occurred=localDateTimeToIso(time);
    if(!occurred){setError("Use date format YYYY-MM-DD HH:mm");return}
    setSaving(true);setError(undefined);
    try {
      await api.post(`/quick-captures/${capture.id}/confirm`,{
        occurred_at:occurred,
        fuel_type:fuelType,
        litres:Number(litres),
        pump_price_per_litre:Number(price),
        discount_amount:Number(discount),
        total_amount:Number(total),
        odometer_km:odometer.trim()?Number(odometer):null,
        full_tank:true,
        missed_previous_fill:false,
        acknowledge_arithmetic_warning:allowArithmetic,
        acknowledge_fuel_type_mismatch:allowFuelMismatch,
        acknowledge_tank_capacity:allowTankCapacity,
        confirm_odometer_conflict:allowOdometerConflict,
      });
      router.replace("/");
    } catch(caught) {
      const message=caught instanceof Error?caught.message:"Could not save";
      const warning = message.toLowerCase();
      if (warning.includes("arithmetic")) setAllowArithmetic(true);
      if (warning.includes("fuel type differs")) setAllowFuelMismatch(true);
      if (warning.includes("tank capacity")) setAllowTankCapacity(true);
      if (warning.includes("odometer conflicts")) setAllowOdometerConflict(true);
      const requiresConsent = warning.includes("arithmetic") || warning.includes("fuel type differs") ||
        warning.includes("tank capacity") || warning.includes("odometer conflicts");
      setError(message + (requiresConsent ? ". Verify the numbers and tap Save again to acknowledge." : ""));
    } finally {
      setSaving(false);
    }
  }

  function field(label:string,value:string,change:(text:string)=>void,unit?:string) {
    return <View style={styles.field}><Text style={styles.label}>{label}{unit?` · ${unit}`:""}</Text>
      <TextInput accessibilityLabel={label} style={styles.input} value={value} onChangeText={change}
        keyboardType={unit==="NZD"||unit==="L"||unit==="km"?"decimal-pad":"default"}/></View>;
  }

  return <ScrollView contentContainerStyle={styles.page}>
    <Pressable onPress={()=>router.back()}><Text style={styles.back}>← Back</Text></Pressable>
    <Text style={styles.title}>Review fuel capture</Text>
    <Text style={styles.description}>Only uncertain or incomplete scans need this step. Check the receipt, correct any values and save privately.</Text>
    {loading?<Text>Loading…</Text>:<>
      {capture?<Text style={styles.status}>Status: {capture.status.replaceAll("_"," ")} {capture.error_code?`· ${capture.error_code.replaceAll("_"," ")}`:""}</Text>:null}
      {field("Date and time",time,setTime)}
      <Text style={styles.label}>Fuel type</Text>
      <View style={styles.choices}>{fuelTypes.map(type=><Pressable key={type}
        accessibilityRole="radio" accessibilityState={{selected:fuelType===type}}
        style={[styles.choice,fuelType===type&&styles.selected]}
        onPress={()=>setFuelType(type)}><Text style={fuelType===type?styles.choiceSelected:styles.choiceText}>{type.replace("PETROL_","Petrol ")}</Text></Pressable>)}</View>
      {field("Litres",litres,setLitres,"L")}
      {field("Pump price per litre",price,setPrice,"NZD")}
      {field("Discount amount",discount,setDiscount,"NZD")}
      {field("Total paid",total,setTotal,"NZD")}
      {field("Odometer (optional)",odometer,setOdometer,"km")}
      {error?<Text accessibilityRole="alert" style={styles.error}>{error}</Text>:null}
      <Pressable accessibilityRole="button" disabled={saving||!capture}
        style={[styles.save,(saving||!capture)&&{opacity:.5}]} onPress={()=>void confirm()}>
        <Text style={styles.saveText}>{saving?"Saving…":"Save fuel record"}</Text></Pressable>
    </>}
  </ScrollView>;
}
const styles=StyleSheet.create({
  page:{padding:24,paddingTop:55,paddingBottom:60,backgroundColor:"#F5F8F6",gap:14},
  title:{fontSize:26,fontWeight:"700",color:"#183B30"},
  back:{color:"#246450",fontSize:16},
  description:{fontSize:14,color:"#536760",lineHeight:21},
  status:{color:"#845C0A",fontWeight:"600",marginBottom:4},
  field:{gap:5},label:{fontSize:14,fontWeight:"600",color:"#213F35"},
  input:{backgroundColor:"#fff",borderRadius:10,borderWidth:1,borderColor:"#C8D7D0",padding:13,fontSize:16,color:"#17362A"},
  choices:{flexDirection:"row",gap:8,flexWrap:"wrap"},
  choice:{backgroundColor:"#fff",paddingVertical:9,paddingHorizontal:12,borderRadius:8,borderWidth:1,borderColor:"#C8D7D0"},
  selected:{backgroundColor:"#175D4D",borderColor:"#175D4D"},
  choiceSelected:{color:"#fff",fontWeight:"600"},
  choiceText:{color:"#2A5143"},
  error:{color:"#A3372B",backgroundColor:"#FCEDEA",padding:12,borderRadius:9},
  save:{backgroundColor:"#175D4D",padding:18,borderRadius:13,alignItems:"center"},
  saveText:{color:"#fff",fontWeight:"700",fontSize:17},
});
