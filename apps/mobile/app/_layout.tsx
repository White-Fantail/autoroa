import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Linking from "expo-linking";
import { AppState } from "react-native";
import { router, Stack } from "expo-router";
import { useEffect, useState } from "react";
import { syncQuickCaptures } from "../lib/capture-queue";
import { api, setAccessToken } from "../lib/api";
import { deleteStoredItem, getStoredItem, setStoredItem } from "../lib/storage";
import { supabase } from "../lib/supabase";
import { nextRoute } from "../lib/workflow";

function captureMode(url: string | null): "receipt" | "full" | null {
  if (!url || !/^autoroa:\/\/\/?quick-capture(?:[?#]|$)/i.test(url)) return null;
  return /[?&]mode=full(?:&|$)/i.test(url) ? "full" : "receipt";
}

export default function Root() {
  const [client] = useState(() => new QueryClient());
  useEffect(() => {
    let initialized = false;
    let activeUser: string | undefined;
    let captureLinkActive = false;

    function openCaptureLink(url: string | null) {
      const mode = captureMode(url);
      if (!mode) return false;
      captureLinkActive = true;
      router.replace({ pathname: "/quick-capture", params: { mode } });
      return true;
    }

    const linkSubscription = Linking.addEventListener("url", ({ url }) => { openCaptureLink(url); });
    const appState = AppState.addEventListener("change", state => {
      if (state === "active") void syncQuickCaptures();
    });

    async function routeSession(session: any) {
      await setAccessToken(session?.access_token ?? null);
      const priorUser = await getStoredItem("autoroa_user_id");
      const nextUser: string | undefined = session?.user?.id;
      if (activeUser !== nextUser) {
        initialized = false;
        captureLinkActive = false;
        activeUser = nextUser;
      }
      if (priorUser && priorUser !== nextUser) {
        await deleteStoredItem(`autoroa_fillup_draft:${priorUser}`);
      }
      if (nextUser) await setStoredItem("autoroa_user_id", nextUser);
      else await deleteStoredItem("autoroa_user_id");
      if (!session) {
        if (!initialized) router.replace(nextRoute({ session: "signed-out", vehicleCount: 0 })!);
        initialized = true;
        return;
      }

      void syncQuickCaptures();
      try {
        const vehicles = await api.get<Array<{ id: string; is_primary: boolean; is_archived?: boolean }>>("/vehicles");
        const primary = vehicles.find(item => item.is_primary && !item.is_archived) ??
          vehicles.find(item => !item.is_archived);
        if (nextUser && primary) {
          await setStoredItem(`autoroa_primary_vehicle:${nextUser}`, primary.id);
        }
        if (captureLinkActive || initialized) return;
        const initialUrl = await Linking.getInitialURL();
        if (primary && openCaptureLink(initialUrl)) {
          initialized = true;
          return;
        }
        if (captureLinkActive) return;
        initialized = true;
        router.replace(nextRoute({ session: "signed-in", vehicleCount: vehicles.length })! as any);
      } catch {
        if (captureLinkActive || initialized) return;
        const initialUrl = await Linking.getInitialURL();
        const cachedVehicle = nextUser ? await getStoredItem(`autoroa_primary_vehicle:${nextUser}`) : null;
        if (cachedVehicle && openCaptureLink(initialUrl)) {
          initialized = true;
          return;
        }
        initialized = true;
        router.replace("/welcome");
      }
    }

    let authSubscription: { unsubscribe: () => void } | undefined;
    try {
      const sessionClient = supabase();
      void sessionClient.auth.getSession().then(({ data }) => routeSession(data.session));
      const { data } = sessionClient.auth.onAuthStateChange((_, session) => {
        void routeSession(session);
      });
      authSubscription = data.subscription;
    } catch {
      router.replace("/welcome");
    }
    return () => {
      authSubscription?.unsubscribe();
      appState.remove();
      linkSubscription.remove();
    };
  }, []);
  return (
    <QueryClientProvider client={client}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="welcome" />
        <Stack.Screen name="onboarding/vehicle" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="fill-up" options={{ presentation: "modal" }} />
        <Stack.Screen name="quick-capture" options={{ presentation: "fullScreenModal" }} />
        <Stack.Screen name="capture-review/[id]" />
        <Stack.Screen name="fill-up/[id]" />
        <Stack.Screen name="vehicle/[id]" />
      </Stack>
    </QueryClientProvider>
  );
}
