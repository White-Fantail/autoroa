import { useEffect, useState } from "react";
import {
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Screen, s } from "../../components/ui";
import { api } from "../../lib/api";
import type { FillUp, Vehicle } from "../../../../packages/types/src";
import { fuelEconomyText } from "../../lib/fuel-economy";
import {
  chooseVehicle,
  fillUpEditRoute,
  vehicleEditRoute,
} from "../../lib/workflow";

const tabs = ["Overview", "Fill-ups", "Economy", "Costs", "Vehicle"] as const;
type CarTab = (typeof tabs)[number];
type Metrics = {
  average_fuel_economy_l_per_100km?: number | string;
  distance_km?: number | string;
  fuel_spend?: number | string;
};

export default function Car() {
  const cache = useQueryClient();
  const [activeTab, setActiveTab] = useState<CarTab>("Overview");
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>();
  const [vehicleSelectorOpen, setVehicleSelectorOpen] = useState(false);
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/vehicles"),
  });
  const vehicle = chooseVehicle(vehicles.data ?? [], selectedVehicleId);

  useEffect(() => {
    if (vehicle && vehicle.id !== selectedVehicleId) {
      setSelectedVehicleId(vehicle.id);
    }
  }, [selectedVehicleId, vehicle]);

  const history = useQuery({
    queryKey: ["fillups", vehicle?.id],
    queryFn: () => api.get<FillUp[]>(`/fill-ups?vehicle_id=${vehicle!.id}`),
    enabled: !!vehicle,
  });
  const metrics = useQuery({
    queryKey: ["car-metrics", vehicle?.id],
    queryFn: () =>
      api.get<Metrics>(`/vehicles/${vehicle!.id}/metrics?period=12m`),
    enabled: !!vehicle,
  });
  const recentFillUps = (history.data ?? []).slice(0, 12).reverse();
  const months = Object.entries(
    (history.data ?? []).reduce<Record<string, number>>((totals, fill) => {
      const month = fill.occurred_at.slice(0, 7);
      totals[month] = (totals[month] ?? 0) + Number(fill.total_amount);
      return totals;
    }, {}),
  )
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-12);

  return (
    <Screen
      title="My Car"
      headerAccessory={vehicle ? (
        <Pressable
          accessibilityRole={vehicles.data && vehicles.data.length > 1 ? "button" : "text"}
          accessibilityLabel={vehicles.data && vehicles.data.length > 1
            ? `Viewing ${vehicle.nickname}. Choose vehicle`
            : `Viewing ${vehicle.nickname}`}
          disabled={!vehicles.data || vehicles.data.length < 2}
          onPress={() => setVehicleSelectorOpen(true)}
          style={({ pressed }) => [styles.headerVehicle, pressed && styles.headerVehiclePressed]}
        >
          <Text style={styles.headerVehicleName} numberOfLines={1}>{vehicle.nickname}</Text>
          {vehicles.data && vehicles.data.length > 1 && <Text style={styles.chevron}>⌄</Text>}
        </Pressable>
      ) : undefined}
    >
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tabList}
        accessibilityRole="tablist"
      >
        {tabs.map((tab) => {
          const selected = activeTab === tab;
          return (
            <Pressable
              key={tab}
              accessibilityRole="tab"
              accessibilityState={{ selected }}
              onPress={() => setActiveTab(tab)}
              style={[styles.tab, selected && styles.tabSelected]}
            >
              <Text style={[styles.tabText, selected && styles.tabTextSelected]}>
                {tab}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {vehicles.isError ? (
        <Card>
          <Text>Could not load your garage. Try again shortly.</Text>
        </Card>
      ) : vehicles.isLoading ? (
        <Text style={s.muted}>Loading your garage…</Text>
      ) : !vehicles.data?.length ? (
        <Card>
          <Text style={styles.sectionTitle}>No vehicles yet</Text>
          <Text style={s.muted}>Add a vehicle to start tracking its fuel use.</Text>
          <Button label="Add vehicle" onPress={() => router.push("/onboarding/vehicle")} />
        </Card>
      ) : (
        <>
          {activeTab === "Overview" && (
            <OverviewTab
              metrics={metrics.data}
              history={history.data ?? []}
              historyIsLoading={history.isLoading}
              historyIsError={history.isError}
            />
          )}
          {activeTab === "Fill-ups" && (
            <FillUpsTab history={history.data} isLoading={history.isLoading} isError={history.isError} />
          )}
          {activeTab === "Economy" && (
            <EconomyTab
              fillUps={recentFillUps}
              isLoading={history.isLoading}
              isError={history.isError}
            />
          )}
          {activeTab === "Costs" && (
            <CostsTab
              fillUps={recentFillUps}
              months={months}
              isLoading={history.isLoading}
              isError={history.isError}
            />
          )}
          {activeTab === "Vehicle" && vehicle && (
            <VehicleTab
              vehicle={vehicle}
              onChanged={() => cache.invalidateQueries({ queryKey: ["vehicles"] })}
            />
          )}
        </>
      )}
      <VehicleSelector
        open={vehicleSelectorOpen}
        vehicles={vehicles.data ?? []}
        selectedVehicleId={vehicle?.id}
        onClose={() => setVehicleSelectorOpen(false)}
        onSelect={(id) => {
          setSelectedVehicleId(id);
          setVehicleSelectorOpen(false);
        }}
      />
    </Screen>
  );
}

function VehicleSelector({
  open,
  vehicles,
  selectedVehicleId,
  onClose,
  onSelect,
}: {
  open: boolean;
  vehicles: Vehicle[];
  selectedVehicleId?: string;
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <Modal
      visible={open}
      transparent
      animationType="slide"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <View style={styles.modalRoot}>
        <Pressable
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          onPress={onClose}
          style={styles.modalBackdrop}
        />
        <View
          accessibilityViewIsModal
          accessibilityLabel="Choose vehicle"
          style={styles.selectorSheet}
        >
          <View style={styles.sheetHandle} />
          <View style={styles.sheetHeader}>
            <Text accessibilityRole="header" style={styles.sectionHeading}>Choose vehicle</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Close vehicle selector" onPress={onClose} style={styles.closeButton}>
              <Text style={styles.closeButtonText}>×</Text>
            </Pressable>
          </View>
          <ScrollView style={styles.selectorList} contentContainerStyle={styles.selectorListContent}>
            {vehicles.map((item) => {
              const selected = item.id === selectedVehicleId;
              return (
                <Pressable
                  key={item.id}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  accessibilityLabel={`${item.nickname}, ${item.year ? `${item.year} ` : ""}${item.make} ${item.model}`}
                  onPress={() => onSelect(item.id)}
                  style={[styles.selectorChoice, selected && styles.selectorChoiceSelected]}
                >
                  <View style={styles.selectorChoiceText}>
                    <View style={styles.vehicleChoiceHeader}>
                      <Text style={[styles.vehicleName, selected && styles.vehicleNameSelected]}>{item.nickname}</Text>
                      {item.is_primary && <Text style={styles.primaryBadge}>PRIMARY</Text>}
                    </View>
                    <Text style={s.muted} numberOfLines={1}>{item.year ? `${item.year} ` : ""}{item.make} {item.model}</Text>
                  </View>
                  <Text style={[styles.radioMark, selected && styles.radioMarkSelected]}>{selected ? "✓" : ""}</Text>
                </Pressable>
              );
            })}
          </ScrollView>
          <Button label="Add another vehicle" onPress={() => { onClose(); router.push("/onboarding/vehicle"); }} />
        </View>
      </View>
    </Modal>
  );
}

function OverviewTab({
  metrics,
  history,
  historyIsLoading,
  historyIsError,
}: {
  metrics?: Metrics;
  history: FillUp[];
  historyIsLoading: boolean;
  historyIsError: boolean;
}) {
  const latest = history[0];
  return (
    <View style={styles.section}>
      <View style={styles.metricRow}>
        <View style={styles.metricCard}>
          <Card>
            <Text style={styles.eyebrow}>AVERAGE ECONOMY</Text>
            <Text style={s.metric}>{metrics?.average_fuel_economy_l_per_100km ?? "—"}</Text>
            <Text style={s.muted}>L/100km · last 12 months</Text>
          </Card>
        </View>
        <View style={styles.metricCard}>
          <Card>
            <Text style={styles.eyebrow}>FUEL COST</Text>
            <Text style={s.metric}>${metrics?.fuel_spend ?? "—"}</Text>
            <Text style={s.muted}>Last 12 months</Text>
          </Card>
        </View>
      </View>
      <Card>
        <Text style={styles.eyebrow}>DISTANCE</Text>
        <Text style={s.metric}>{metrics?.distance_km ?? "—"} km</Text>
        <Text style={s.muted}>Recorded over the last 12 months</Text>
      </Card>
      <Card>
        <Text style={styles.eyebrow}>LATEST FILL-UP</Text>
        {historyIsLoading ? (
          <Text style={s.muted}>Loading latest fill-up…</Text>
        ) : historyIsError ? (
          <Text>Latest fill-up could not be loaded.</Text>
        ) : latest ? (
          <>
            <Text style={styles.sectionTitle}>{latest.litres} L · ${latest.total_amount}</Text>
            <Text style={s.muted}>{new Date(latest.occurred_at).toLocaleDateString("en-NZ")}</Text>
            <Pressable onPress={() => router.push(fillUpEditRoute(latest.id) as never)}>
              <Text style={s.link}>View fill-up →</Text>
            </Pressable>
          </>
        ) : (
          <Text style={s.muted}>No fill-ups recorded yet.</Text>
        )}
      </Card>
    </View>
  );
}

function FillUpsTab({ history, isLoading, isError }: { history?: FillUp[]; isLoading: boolean; isError: boolean }) {
  if (isLoading) return <Text style={s.muted}>Loading fill-ups…</Text>;
  if (isError) return <Card><Text>Fill-up history could not be loaded.</Text></Card>;
  if (!history?.length) return <Card><Text>No fill-ups yet. Tap + after your next fuel stop.</Text></Card>;
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeading}>Fill-up history</Text>
      {history.map((fill) => (
        <Pressable key={fill.id} onPress={() => router.push(fillUpEditRoute(fill.id) as never)}>
          <Card>
            <Text style={s.muted}>{new Date(fill.occurred_at).toLocaleDateString("en-NZ")}</Text>
            <Text style={styles.sectionTitle}>{fill.litres} L · ${fill.total_amount}</Text>
            <Text>{fill.pump_price_per_litre ?? "—"}/L · {fuelEconomyText(fill)}</Text>
            <Text style={s.link}>Edit fill-up →</Text>
          </Card>
        </Pressable>
      ))}
    </View>
  );
}

function EconomyTab({ fillUps, isLoading, isError }: { fillUps: FillUp[]; isLoading: boolean; isError: boolean }) {
  if (isLoading) return <Text style={s.muted}>Loading economy history…</Text>;
  if (isError) return <Card><Text>Economy history could not be loaded.</Text></Card>;
  const values = fillUps.filter((fill) => Number(fill.fuel_economy_l_per_100km) > 0);
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeading}>Economy trend</Text>
      <Text style={s.muted}>Lower fuel consumption is better.</Text>
      {values.length ? (
        <Chart
          values={values.map((fill) => Number(fill.fuel_economy_l_per_100km))}
          labels={values.map((fill) => `${new Date(fill.occurred_at).toLocaleDateString("en-NZ")}: ${fill.fuel_economy_l_per_100km} L/100km`)}
          color="#16A085"
        />
      ) : <Card><Text style={s.muted}>Economy appears after two compatible full-tank fill-ups.</Text></Card>}
    </View>
  );
}

function CostsTab({ fillUps, months, isLoading, isError }: { fillUps: FillUp[]; months: [string, number][]; isLoading: boolean; isError: boolean }) {
  if (isLoading) return <Text style={s.muted}>Loading cost history…</Text>;
  if (isError) return <Card><Text>Cost history could not be loaded.</Text></Card>;
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeading}>Monthly fuel spend</Text>
      {months.length ? <Chart values={months.map(([, total]) => total)} labels={months.map(([month, total]) => `${month}: $${total.toFixed(2)}`)} color="#9A6700" /> : <Card><Text style={s.muted}>No cost data recorded yet.</Text></Card>}
      <Text style={styles.sectionHeading}>Price per litre</Text>
      {fillUps.length ? <Chart values={fillUps.map((fill) => Number(fill.pump_price_per_litre ?? 0))} labels={fillUps.map((fill) => `${new Date(fill.occurred_at).toLocaleDateString("en-NZ")}: $${fill.pump_price_per_litre ?? "—"} per litre`)} color="#345995" /> : <Card><Text style={s.muted}>No price data recorded yet.</Text></Card>}
    </View>
  );
}

function Chart({ values, labels, color }: { values: number[]; labels: string[]; color: string }) {
  const maximum = Math.max(...values, 1);
  return (
    <Card>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chart}>
        {values.map((value, index) => (
          <View key={`${labels[index]}-${index}`} style={styles.barColumn} accessibilityLabel={labels[index]}>
            <Text style={styles.barValue}>{value.toFixed(value < 10 ? 2 : 0)}</Text>
            <View style={[styles.bar, { height: Math.max(6, (value / maximum) * 100), backgroundColor: color }]} />
          </View>
        ))}
      </ScrollView>
    </Card>
  );
}

function VehicleTab({ vehicle, onChanged }: { vehicle: Vehicle; onChanged: () => Promise<unknown> }) {
  return (
    <View style={styles.section}>
      <Card>
        <View style={styles.vehicleChoiceHeader}>
          <Text style={styles.sectionTitle}>{vehicle.nickname}</Text>
          {vehicle.is_primary && <Text style={styles.primaryBadge}>PRIMARY</Text>}
        </View>
        <Text style={s.muted}>{vehicle.year ? `${vehicle.year} ` : ""}{vehicle.make} {vehicle.model}</Text>
        <Text style={s.muted}>{vehicle.fuel_type.replaceAll("_", " ")}</Text>
        {!vehicle.is_primary && (
          <Pressable onPress={async () => { await api.patch(`/vehicles/${vehicle.id}`, { is_primary: true }); await onChanged(); }}>
            <Text style={s.link}>Make primary vehicle</Text>
          </Pressable>
        )}
        <Pressable accessibilityRole="link" onPress={() => router.push(vehicleEditRoute(vehicle.id) as never)}>
          <Text style={s.link}>Edit vehicle →</Text>
        </Pressable>
        <Pressable onPress={() => Alert.alert("Archive vehicle?", `${vehicle.nickname} will leave the active garage.`, [
          { text: "Cancel", style: "cancel" },
          { text: "Archive", style: "destructive", onPress: async () => { await api.delete(`/vehicles/${vehicle.id}`); await onChanged(); } },
        ])}>
          <Text style={s.danger}>Archive vehicle</Text>
        </Pressable>
      </Card>
      <Button label="Add another vehicle" onPress={() => router.push("/onboarding/vehicle")} />
    </View>
  );
}

const styles = StyleSheet.create({
  tabList: { borderBottomColor: "#D4E2DF", borderBottomWidth: 1, gap: 4 },
  tab: { minHeight: 44, justifyContent: "center", paddingHorizontal: 12, borderBottomWidth: 3, borderBottomColor: "transparent" },
  tabSelected: { borderBottomColor: "#16A085" },
  tabText: { color: "#587074", fontSize: 15, fontWeight: "600" },
  tabTextSelected: { color: "#102A2E", fontWeight: "800" },
  headerVehicle: { minHeight: 40, maxWidth: "100%", flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 5, borderRadius: 12, paddingHorizontal: 10, backgroundColor: "#EAF8F4" },
  headerVehiclePressed: { opacity: 0.7 },
  headerVehicleName: { color: "#087E6B", fontSize: 15, fontWeight: "800", flexShrink: 1 },
  chevron: { color: "#087E6B", fontSize: 18, fontWeight: "800", marginTop: -4 },
  vehicleChoiceHeader: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  vehicleName: { color: "#405A5D", fontSize: 16, fontWeight: "600", flexShrink: 1 },
  vehicleNameSelected: { color: "#102A2E", fontWeight: "800" },
  primaryBadge: { color: "#087E6B", backgroundColor: "#DDF4EE", borderRadius: 999, paddingHorizontal: 7, paddingVertical: 3, fontSize: 10, fontWeight: "800" },
  eyebrow: { color: "#587074", fontSize: 12, fontWeight: "800", letterSpacing: 0.7 },
  section: { gap: 12 },
  sectionHeading: { color: "#102A2E", fontSize: 20, fontWeight: "800" },
  sectionTitle: { color: "#102A2E", fontSize: 20, fontWeight: "700" },
  metricRow: { flexDirection: "row", gap: 10 },
  metricCard: { flex: 1 },
  chart: { height: 140, alignItems: "flex-end", gap: 10, paddingTop: 10 },
  barColumn: { width: 34, height: 130, justifyContent: "flex-end", alignItems: "center", gap: 5 },
  bar: { width: 22, borderRadius: 5 },
  barValue: { color: "#587074", fontSize: 10 },
  modalRoot: { flex: 1, justifyContent: "flex-end" },
  modalBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(16, 42, 46, 0.45)" },
  selectorSheet: { maxHeight: "78%", backgroundColor: "#F6FAF9", borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 20, paddingTop: 10, paddingBottom: 24, gap: 14 },
  sheetHandle: { width: 42, height: 5, borderRadius: 999, backgroundColor: "#B8C8C5", alignSelf: "center" },
  sheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  closeButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderRadius: 22 },
  closeButtonText: { color: "#405A5D", fontSize: 30, lineHeight: 32 },
  selectorList: { flexGrow: 0 },
  selectorListContent: { gap: 10 },
  selectorChoice: { minHeight: 70, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1.5, borderColor: "#D4E2DF", borderRadius: 14, padding: 12, backgroundColor: "#FFFFFF" },
  selectorChoiceSelected: { borderColor: "#16A085", backgroundColor: "#EAF8F4" },
  selectorChoiceText: { flex: 1, gap: 5 },
  radioMark: { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, borderColor: "#7E9591", color: "#FFFFFF", textAlign: "center", lineHeight: 21, fontWeight: "800" },
  radioMarkSelected: { borderColor: "#16A085", backgroundColor: "#16A085" },
});
