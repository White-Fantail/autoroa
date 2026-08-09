import { useEffect, useState } from "react";
import {deleteStoredItem,getStoredItem,setStoredItem} from "../lib/storage";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { fillUpSchema } from "../../../packages/validation/src";
import {z} from 'zod';
import { router } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { Pressable, Switch, Text, TextInput, View } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Card, Screen, s } from "../components/ui";
import { api, uploadImage } from "../lib/api";
import {isOdometerSequenceConflict,restoredFillUpStep} from "../lib/workflow";
import type { FuelType, Vehicle } from "../../../packages/types/src";
import {useReviewState} from '../lib/review-state';
type Form = {
  station_id?: string;
  occurred_at: string;
  fuel_type: FuelType;
  litres: string;
  pump_price_per_litre: string;
  discount_amount: string;
  total_amount: string;
  odometer_km: string;
};
const initial: Form = {
  occurred_at: new Date().toISOString(),
  fuel_type: "PETROL_91",
  litres: "",
  pump_price_per_litre: "",
  discount_amount: "0",
  total_amount: "",
  odometer_km: "",
};
const reviewSchema=z.object({station_id:z.string().uuid().optional(),occurred_at:z.string().datetime(),fuel_type:z.enum(['PETROL_91','PETROL_95','PETROL_98','DIESEL','OTHER']),litres:z.string().refine(x=>Number.isFinite(Number(x))&&Number(x)>0,'Enter positive litres'),pump_price_per_litre:z.string().refine(x=>Number.isFinite(Number(x))&&Number(x)>0,'Enter a positive price'),discount_amount:z.string().refine(x=>Number.isFinite(Number(x))&&Number(x)>=0,'Enter a valid discount'),total_amount:z.string().refine(x=>Number.isFinite(Number(x))&&Number(x)>0,'Enter a positive total'),odometer_km:z.string().refine(x=>Number.isInteger(Number(x))&&Number(x)>=0,'Enter a valid odometer')});
const draftSchema=z.object({form:reviewSchema,step:z.number().int().min(0).max(4),vehicle:z.string().uuid().optional(),receipt:z.object({id:z.string().uuid()}).passthrough().optional(),odometerImage:z.string().uuid().optional(),odometerConfidence:z.number().min(0).max(1).optional(),full:z.boolean(),missed:z.boolean(),stations:z.array(z.record(z.string(),z.unknown()))});
export default function FillUp() {
  const cache = useQueryClient();
  const [step, setStep] = useState(0);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehicle, setVehicle] = useState<string>();
  const [receipt, setReceipt] = useState<any>();
  const [stations, setStations] = useState<any[]>([]);
  const [odometerImage, setOdometerImage] = useState<string>();
  const [odometerConfidence, setOdometerConfidence] = useState<number>();
  const reviewState=useReviewState();const {full,setFull,saving,error,setError}=reviewState;
  const [missed, setMissed] = useState(false);
  const [result, setResult] = useState<any>();
  const [fillHistory, setFillHistory] = useState<Array<{occurred_at:string;odometer_km:number}>>([]);
  const [warningsAccepted, setWarningsAccepted] = useState(false);
  const [sequenceRejected, setSequenceRejected] = useState(false);
  const [stationSearch, setStationSearch] = useState("");
  const validatedForm = useForm<Form>({ resolver: zodResolver(reviewSchema),defaultValues:initial });
  const form=validatedForm.watch();
  const [draftKey,setDraftKey]=useState<string>();
  useEffect(() => {
    load();
    getStoredItem('carfolio_user_id').then(userId=>{if(!userId)return;const key=`carfolio_fillup_draft:${userId}`;setDraftKey(key);getStoredItem(key).then(async(draft) => {
      if (!draft) return;
      try {
        const saved = draftSchema.parse(JSON.parse(draft));
        if(saved.vehicle)await api.get(`/vehicles/${saved.vehicle}`);
        const restoredReceipt=saved.receipt as {id?:string}|undefined;if(restoredReceipt?.id)await api.get(`/receipts/${restoredReceipt.id}`);
        if(saved.odometerImage)await api.get(`/media/${saved.odometerImage}`);
        if(saved.form.station_id)await api.get(`/fuel-stations/${saved.form.station_id}`);
        validatedForm.reset(saved.form);
        if (Number.isInteger(saved.step)) setStep(restoredFillUpStep(saved.step));
        setVehicle(saved.vehicle);
        setReceipt(saved.receipt);
        setOdometerImage(saved.odometerImage);
        setOdometerConfidence(saved.odometerConfidence);
        setFull(saved.full ?? true);
        setMissed(saved.missed ?? false);
        setStations(Array.isArray(saved.stations) ? saved.stations : []);
      } catch {
        deleteStoredItem(key);
      }
    })});
  }, []);
  useEffect(() => {
    if (!draftKey) return;
    if (step === 4) {
      deleteStoredItem(draftKey);
      return;
    }
    setStoredItem(
      draftKey,
      JSON.stringify({
        form,
        step,
        vehicle,
        receipt,
        odometerImage,
        odometerConfidence,
        full,
        missed,
        stations,
      }),
    );
  }, [draftKey,form, step, vehicle, receipt, odometerImage, odometerConfidence, full, missed, stations]);
  useEffect(()=>setSequenceRejected(false),[form.occurred_at,form.odometer_km,vehicle]);
  async function load() {
    try {
      const rows = await api.get<Vehicle[]>("/vehicles");
      setVehicles(rows);
      setVehicle(rows.find((x) => x.is_primary)?.id ?? rows[0]?.id);
      const selected = rows.find((x) => x.is_primary)?.id ?? rows[0]?.id;
      if (selected) {
        const history = await api.get<any[]>(
          `/fill-ups?vehicle_id=${selected}&limit=100`,
        );
        setFillHistory(history);
      }
    } catch {
      setError("Could not load vehicles. Check your connection and retry.");
    }
  }
  async function pick(kind: "RECEIPT" | "ODOMETER", camera: boolean) {
    setError(undefined);
    try {
      const permission = camera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) throw new Error("Permission was not granted");
      const chosen = camera
        ? await ImagePicker.launchCameraAsync({
            mediaTypes: ["images"],
            quality: 0.8,
          })
        : await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ["images"],
            quality: 0.8,
          });
      if (chosen.canceled) return;
      const media = await uploadImage(chosen.assets[0].uri, kind);
      if (kind === "RECEIPT") {
        const created = await api.post<any>("/receipts", {
          media_asset_id: media.id,
        });
        const parsed = await api.post<any>(
          `/receipts/${created.id}/process`,
          {},
        );
        setReceipt(parsed);
        setStations(
          await api.get<any[]>(`/receipts/${created.id}/station-candidates`),
        );
        validatedForm.reset({
          ...validatedForm.getValues(),
          occurred_at: parsed.transaction_datetime ?? validatedForm.getValues('occurred_at'),
          fuel_type: parsed.fuel_type ?? validatedForm.getValues('fuel_type'),
          litres: parsed.litres ?? "",
          pump_price_per_litre: parsed.pump_price_per_litre ?? "",
          discount_amount: parsed.discount_amount ?? "0",
          total_amount: parsed.total_amount ?? "",
        });
      } else {
        setOdometerImage(media.id);
        if (vehicle) {
          const created = await api.post<any>("/odometer-readings", {
            media_asset_id: media.id,
            vehicle_id: vehicle,
          });
          const parsed = await api.post<any>(
            `/odometer-readings/${created.id}/process`,
            {},
          );
          setOdometerConfidence(parsed.confidence ?? undefined);
          if (parsed.reading_km != null)
            validatedForm.setValue('odometer_km',String(parsed.reading_km),{shouldValidate:true});
        }
      }
      setStep((x) => x + 1);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Image processing failed. Retry without losing your entries.",
      );
    }
  }
  async function save() {
    const candidate = {
      ...form,
      vehicle_id: vehicle,
      station_id: form.station_id || undefined,
      litres: Number(form.litres),
      pump_price_per_litre: Number(form.pump_price_per_litre),
      total_amount: Number(form.total_amount),
      odometer_km: Number(form.odometer_km),
      full_tank: full,
      missed_previous_fill: missed,
    };
    const valid = fillUpSchema.safeParse(candidate);
    if (!valid.success || !(await validatedForm.trigger())) {
      setError(
        valid.success
          ? "Review invalid fields."
          : (valid.error.issues[0]?.message ?? "Review invalid fields."),
      );
      return;
    }
    await reviewState.submit(true,async()=>{
      if (receipt)
        await api.post(`/receipts/${receipt.id}/confirm`, {
          station_id: form.station_id,
          station_text: receipt.station_text,
          fuel_type: form.fuel_type,
          litres: form.litres,
          pump_price_per_litre: form.pump_price_per_litre,
          discount_amount: form.discount_amount,
          total_amount: form.total_amount,
          transaction_datetime: form.occurred_at,
          acknowledge_arithmetic_warning: warningsAccepted,
        });
      let saved;
      try{saved = await api.post<any>(
        `/fill-ups?confirm_lower_odometer=${warningsAccepted}`,
        {
          vehicle_id: vehicle,
          station_id: form.station_id,
          occurred_at: form.occurred_at,
          fuel_type: form.fuel_type,
          litres: form.litres,
          pump_price_per_litre: form.pump_price_per_litre,
          total_amount: form.total_amount,
          discount_amount: form.discount_amount,
          odometer_km: Number(form.odometer_km),
          full_tank: full,
          missed_previous_fill: missed,
          acknowledge_fuel_type_mismatch: warningsAccepted,
          acknowledge_tank_capacity: warningsAccepted,
          acknowledge_arithmetic_warning: warningsAccepted,
          receipt_id: receipt?.id,
          odometer_image_id: odometerImage,
        },
      )}catch(error){if(isOdometerSequenceConflict(error))setSequenceRejected(true);throw error}
      setResult(saved);
      if(draftKey)await deleteStoredItem(draftKey);
      await cache.invalidateQueries();
      setStep(4);
    });
  }
  if (step === 0)
    return (
      <Screen title="Add fill-up">
        {!vehicles.length && <Button label="Load vehicles" onPress={load} />}{" "}
        {vehicles.map((x) => (
          <Pressable
            key={x.id}
            onPress={async () => {
              setVehicle(x.id);
              const history = await api.get<any[]>(
                `/fill-ups?vehicle_id=${x.id}&limit=100`,
              );
              setFillHistory(history);
            }}
          >
            <Card>
              <Text>
                {x.nickname}
                {x.id === vehicle ? " · Selected" : ""}
              </Text>
            </Card>
          </Pressable>
        ))}
        <Button
          label="Continue"
          disabled={!vehicle}
          onPress={() => setStep(1)}
        />
        {error && <Text>{error}</Text>}
      </Screen>
    );
  if (step === 1)
    return (
      <Screen title="Scan receipt">
        <Text style={s.muted}>
          Camera access scans your receipt. Every extracted value remains
          editable.
        </Text>
        <Button label="Take photo" onPress={() => pick("RECEIPT", true)} />
        <Button
          label="Choose existing photo"
          onPress={() => pick("RECEIPT", false)}
        />
        <Button label="Skip receipt" onPress={() => setStep(2)} />
        {error && <Text>{error}</Text>}
      </Screen>
    );
  if (step === 2)
    return (
      <Screen title="Scan odometer">
        <Text style={s.muted}>
          Capture the main odometer—not trip or range. You may enter it manually
          next.
        </Text>
        <Button label="Take photo" onPress={() => pick("ODOMETER", true)} />
        <Button label="Choose photo" onPress={() => pick("ODOMETER", false)} />
        <Button label="Enter manually" onPress={() => setStep(3)} />
        {error && <Text>{error}</Text>}
      </Screen>
    );
  if (step === 3) {
    const arithmeticMismatch =
      Math.abs(
        Number(form.litres) * Number(form.pump_price_per_litre) -
          Number(form.discount_amount || 0) -
          Number(form.total_amount),
      ) > Math.max(2, Number(form.total_amount) * 0.1);
    const occurredAt=new Date(form.occurred_at).getTime();const ordered=fillHistory.slice().sort((a,b)=>new Date(a.occurred_at).getTime()-new Date(b.occurred_at).getTime());const previous=ordered.filter(item=>new Date(item.occurred_at).getTime()<occurredAt).at(-1);const next=ordered.find(item=>new Date(item.occurred_at).getTime()>occurredAt);const odometerSequenceWarning=sequenceRejected||(previous!=null&&Number(form.odometer_km)<previous.odometer_km)||(next!=null&&Number(form.odometer_km)>next.odometer_km);
    return (
      <Screen title="Review">
        <Text style={s.muted}>
          Review every value. Fields under 70% confidence require attention.
        </Text>
        <Text>Station</Text>
        {receipt&&<Text style={{color:Number(receipt.station_confidence??0)<.7?'#9A6700':'#345995'}}>{receipt.station_text??'No station extracted'} · {Number(receipt.station_confidence??0)>=.9?'High confidence':Number(receipt.station_confidence??0)>=.7?'Review':'Needs attention'}{form.station_id?` · match ${Math.round(Number(stations.find(item=>item.id===form.station_id)?.match_confidence??0)*100)}%`:' · choose or search to correct'}</Text>}
        <TextInput
          placeholder="Search station, city, or address"
          value={stationSearch}
          onChangeText={setStationSearch}
          onSubmitEditing={async () =>
            setStations(
              await api.get<any[]>(
                `/fuel-stations/search?q=${encodeURIComponent(stationSearch)}`,
              ),
            )
          }
        />
        {stations.map((station) => (
          <Pressable
            key={station.id}
            onPress={() =>
              validatedForm.setValue('station_id',station.id,{shouldValidate:true})
            }
          >
            <Card>
              <Text>
                {station.name}
                {form.station_id === station.id ? " · Selected" : ""}
              </Text>
              <Text style={s.muted}>
                {station.address ?? station.address_line}
              </Text>
            </Card>
          </Pressable>
        ))}
        {!stations.length && (
          <Pressable
            onPress={() =>
              validatedForm.setValue('station_id',undefined)
            }
          >
            <Text style={s.muted}>
              Can't find the station — save privately without a public price
              observation.
            </Text>
          </Pressable>
        )}
        {arithmeticMismatch && (
          <Text accessibilityRole="alert">
            Receipt arithmetic differs from litres × price. This can be valid
            for discounts or other purchases.
          </Text>
        )}
        {odometerSequenceWarning && (
          <Text accessibilityRole="alert">
            Odometer conflicts with a reading before or after this date. Check
            the vehicle, trip meter, OCR value, and fill-up date.
          </Text>
        )}
        {(arithmeticMismatch || odometerSequenceWarning) && (
          <View
            style={{ flexDirection: "row", justifyContent: "space-between" }}
          >
            <Text>I checked these warnings</Text>
            <Switch
              value={warningsAccepted}
              onValueChange={setWarningsAccepted}
            />
          </View>
        )}
        {Object.entries(form)
          .filter(([key]) => key !== "station_id")
          .map(([key, value]) => (
            <View key={key}>
              <Text>
                {key.replaceAll("_", " ")}
                {(()=>{const map:Record<string,string>={occurred_at:'datetime_confidence',fuel_type:'fuel_type_confidence',litres:'litres_confidence',pump_price_per_litre:'price_confidence',discount_amount:'discount_confidence',total_amount:'total_confidence'};const confidence=key==='odometer_km'?odometerConfidence:receipt?.[map[key]];return confidence==null?'':` · ${confidence>=.9?'High confidence':confidence>=.7?'Review':'Needs attention'}`})()}
              </Text>
              <Controller control={validatedForm.control} name={key as keyof Form} render={({field,fieldState})=>{const map:Record<string,string>={occurred_at:'datetime_confidence',fuel_type:'fuel_type_confidence',litres:'litres_confidence',pump_price_per_litre:'price_confidence',discount_amount:'discount_confidence',total_amount:'total_confidence'};const confidence=key==='odometer_km'?odometerConfidence:receipt?.[map[key]];return <><TextInput accessibilityLabel={key} value={String(field.value??'')} onChangeText={field.onChange} onBlur={field.onBlur} style={{backgroundColor:"white",borderWidth:2,borderColor:fieldState.error?'#C9372C':confidence!=null&&confidence<.7?'#9A6700':'#D4E2DF',padding:12,borderRadius:10}}/>{fieldState.error&&<Text accessibilityRole="alert">{fieldState.error.message}</Text>}</>}}/>
            </View>
          ))}
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text>Full tank?</Text>
          <Switch value={full} onValueChange={setFull} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text>I may have missed a fill-up</Text>
          <Switch value={missed} onValueChange={setMissed} />
        </View>
        <Button
          label={saving ? "Saving…" : "Save fill-up"}
          disabled={
            saving ||
            ((arithmeticMismatch || odometerSequenceWarning) && !warningsAccepted)
          }
          onPress={save}
        />
        {error && <Text accessibilityRole="alert">{error}</Text>}
      </Screen>
    );
  }
  if (!result)
    return (
      <Screen title="Fill-up not saved">
        <Text accessibilityRole="alert">
          The saved result is unavailable. Return to review and try again.
        </Text>
        <Button label="Return to review" onPress={() => setStep(3)} />
      </Screen>
    );
  return (
    <Screen title="Fill-up saved">
      <Card>
        <Text style={s.metric}>
          {result.litres} L · ${result.total_amount}
        </Text>
        {result.fuel_economy_l_per_100km ? (
          <Text>
            {result.distance_since_previous_km} km ·{" "}
            {result.fuel_economy_l_per_100km} L/100km · ${result.cost_per_100km}
            /100km
          </Text>
        ) : (
          <Text>
            Fuel economy will be calculated after enough full-tank data is
            available.
          </Text>
        )}
      </Card>
      <Button label="Done" onPress={() => router.replace("/(tabs)")} />
    </Screen>
  );
}
