import { Alert, Pressable, Text } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { Card, FormField, Screen, s } from "../../components/ui";
import { api, setAccessToken } from "../../lib/api";
import {deleteStoredItem,getStoredItem} from '../../lib/storage';
import {useState} from 'react';
export default function Profile() {
  async function clearDraft(){const user=await getStoredItem('autoroa_user_id');if(user)await deleteStoredItem(`autoroa_fillup_draft:${user}`)}
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<any>("/me") });
  const cache=useQueryClient();
  const [updateError,setUpdateError]=useState('');async function update(values:Record<string,string>){try{setUpdateError('');await api.patch('/me',values);await cache.invalidateQueries({queryKey:['me']})}catch(e){setUpdateError(e instanceof Error?e.message:'Profile update failed')}}
  const remove = useMutation({
    mutationFn: () => api.delete("/me"),
    onSuccess: async () => {
      await setAccessToken(null);
      await clearDraft();
      router.replace("/");
    },
  });
  return (
    <Screen title="Profile">
      <Card>
        <FormField label="Display name" placeholder="Enter your display name" defaultValue={me.data?.display_name??''} onSubmitEditing={event=>update({display_name:event.nativeEvent.text})}/><Text style={s.muted}>Press Enter to save</Text>
      </Card>
      <Card>
        <Text>Units</Text><Text>{me.data?.preferred_distance_unit ?? "km"} · {me.data?.preferred_efficiency_unit ?? "L_PER_100KM"}</Text>
      </Card>
      <Card>
        <Text>Currency · {me.data?.preferred_currency??'NZD'}</Text>
      </Card>
      <Card>
        <Text>Privacy</Text>
      </Card>
      <Pressable
        onPress={async () => {
          await setAccessToken(null);
          await clearDraft();
          router.replace("/");
        }}
      >
        <Card>
          <Text>Sign out</Text>
        </Card>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => Alert.alert('Delete account?','Private media and vehicle history will be permanently removed.',[{text:'Cancel',style:'cancel'},{text:'Delete',style:'destructive',onPress:()=>remove.mutate()}])}>
        <Card>
          <Text>Delete account and private data</Text>
        </Card>
      </Pressable>
      {remove.isError && (
        <Text>Account deletion failed. Nothing was changed; retry later.</Text>
      )}
      {updateError&&<Text accessibilityRole="alert">{updateError}</Text>}
    </Screen>
  );
}
