import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { router, Stack } from "expo-router";
import { useEffect, useState } from "react";
import * as Linking from "expo-linking";
import { AppState } from "react-native";
import { syncLocalCaptures } from "../lib/capture-queue";
import { api, setAccessToken } from "../lib/api";
import { deleteStoredItem, getStoredItem, setStoredItem } from "../lib/storage";
import { supabase } from "../lib/supabase";
import {nextRoute} from '../lib/workflow';
export default function Root() {
  const [client] = useState(() => new QueryClient());
  useEffect(() => {
    let consumedInitialLink = false;
    const subscription = AppState.addEventListener("change", state => { if (state === "active") void syncLocalCaptures(); });
    async function routeSession(session: any) {
      await setAccessToken(session?.access_token ?? null);
      const priorUser=await getStoredItem('autoroa_user_id');const nextUser=session?.user?.id;
      if(priorUser&&priorUser!==nextUser)await deleteStoredItem(`autoroa_fillup_draft:${priorUser}`);
      if(nextUser)await setStoredItem('autoroa_user_id',nextUser);else if(priorUser)await deleteStoredItem(`autoroa_fillup_draft:${priorUser}`);
      if (!session) return router.replace(nextRoute({session:'signed-out',vehicleCount:0})!);
      try {
        const vehicles = await api.get<unknown[]>("/vehicles");
        if (vehicles.length && !consumedInitialLink) {
          const url = await Linking.getInitialURL();
          if (url && /quick-capture/i.test(url)) {
            consumedInitialLink = true;
            router.replace({ pathname: "/quick-capture", params: { mode: url.includes("mode=full") ? "full" : "receipt" } });
            void syncLocalCaptures();
            return;
          }
        }
        router.replace(nextRoute({session:'signed-in',vehicleCount:vehicles.length})! as any);
        void syncLocalCaptures();
      } catch {
        router.replace("/welcome");
      }
    }
    try {
      const client = supabase();
      client.auth.getSession().then(({ data }) => routeSession(data.session));
      const { data } = client.auth.onAuthStateChange(async (_, session) => {
        await routeSession(session);
      });
      return () => { data.subscription.unsubscribe(); subscription.remove(); };
    } catch {
      subscription.remove();
      router.replace("/welcome");
    }
  }, []);
  return (
    <QueryClientProvider client={client}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="welcome" />
        <Stack.Screen name="onboarding/vehicle" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="fill-up" options={{ presentation: "modal" }} />
        <Stack.Screen name="quick-capture" />
        <Stack.Screen name="fill-up/[id]" />
        <Stack.Screen name="vehicle/[id]" />
      </Stack>
    </QueryClientProvider>
  );
}
