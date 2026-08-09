import {useEffect,useState} from 'react';
import {Pressable,Text,View} from 'react-native';
import {router,useLocalSearchParams} from 'expo-router';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import type {Vehicle} from '../../../../packages/types/src';
import {Button,Card,FormField,Screen,s} from '../../components/ui';
import {api} from '../../lib/api';
import {fuels,vehicleEditSchema} from '../../lib/car-validation';

export default function EditVehicle(){
  const {id}=useLocalSearchParams<{id:string}>();const cache=useQueryClient();
  const vehicle=useQuery({queryKey:['vehicle',id],queryFn:()=>api.get<Vehicle>(`/vehicles/${id}`),enabled:!!id});
  const [edit,setEdit]=useState<any>();const [error,setError]=useState('');const [saving,setSaving]=useState(false);
  useEffect(()=>{if(vehicle.data)setEdit({...vehicle.data})},[vehicle.data]);
  async function save(){const parsed=vehicleEditSchema.safeParse(edit);if(!parsed.success){setError(parsed.error.issues[0]?.message??'Check the highlighted values.');return}try{setSaving(true);setError('');await api.patch(`/vehicles/${id}`,parsed.data);await cache.invalidateQueries({queryKey:['vehicles']});router.back()}catch(caught){setError(caught instanceof Error?caught.message:'Vehicle could not be saved.')}finally{setSaving(false)}}
  return <Screen title="Edit vehicle">
    <Pressable accessibilityRole="link" onPress={()=>router.back()}><Text style={s.link}>← Back to My Car</Text></Pressable>
    {vehicle.isLoading&&<Text>Loading vehicle…</Text>}{vehicle.isError&&<Text accessibilityRole="alert">Vehicle could not be loaded.</Text>}
    {edit&&<Card>
      <Text style={s.muted}>Fields with an outlined box can be edited.</Text>
      {[['nickname','Nickname'],['make','Make'],['model','Model'],['year','Year'],['variant','Variant'],['registration_plate','Registration plate'],['tank_capacity_litres','Tank capacity (litres)']].map(([key,label])=><FormField key={key} label={label} value={String(edit[key]??'')} onChangeText={value=>setEdit((current:any)=>({...current,[key]:value}))}/>)}
      <Text style={s.fieldLabel}>Fuel type</Text><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{fuels.map(fuel=><Pressable accessibilityRole="radio" accessibilityState={{selected:edit.fuel_type===fuel}} style={[s.choice,edit.fuel_type===fuel&&s.choiceSelected]} key={fuel} onPress={()=>setEdit((current:any)=>({...current,fuel_type:fuel}))}><Text>{fuel}{edit.fuel_type===fuel?' ✓':''}</Text></Pressable>)}</View>
      {error&&<Text accessibilityRole="alert">{error}</Text>}<Button label={saving?'Saving…':'Save vehicle'} disabled={saving} onPress={()=>void save()}/><Pressable accessibilityRole="button" onPress={()=>router.back()}><Text style={s.link}>Cancel</Text></Pressable>
    </Card>}
  </Screen>
}
