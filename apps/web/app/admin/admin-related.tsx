"use client";

import React, { useEffect, useState } from "react";
import { AdminRow, formatAdminValue, humanizeField } from "./admin-utils";

export type Relation = {
  field: string;
  title: string;
  target?: string;
  endpoint?: string;
  summaryFields: string[];
};

export function RelatedEntity({ apiBase, relation, relatedId, token, onOpenRelated }: {
  apiBase: string;
  relation: Relation;
  relatedId: unknown;
  token: string;
  onOpenRelated: (section: string, row: AdminRow) => void;
}) {
  const [related, setRelated] = useState<AdminRow>();
  const [loading, setLoading] = useState(false);
  const id = String(relatedId ?? "");

  useEffect(() => {
    setRelated(undefined);
    if (!id) return;
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    fetch(`${apiBase}/admin/${relation.endpoint ?? relation.target}/${id}`, {
      headers: { authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((item: AdminRow) => {
        if (active) setRelated(item);
      })
      .catch(() => {
        if (active) setRelated(undefined);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [apiBase, id, relation.endpoint, relation.target, token]);

  if (!id) return null;
  return (
    <section className="admin-detail-section admin-related-section">
      <header>
        <div>
          <p className="admin-kicker">Related record</p>
          <h2>{relation.title}</h2>
        </div>
        {related && relation.target && (
          <button onClick={() => onOpenRelated(relation.target!, related!)}>
            View {relation.title.toLowerCase()} →
          </button>
        )}
      </header>
      {loading ? <p className="admin-related-status">Loading related information…</p> : related ? (
        <dl className="admin-related-summary">
          {relation.summaryFields.filter((field) => field in related).map((field) => (
            <div key={field}><dt>{humanizeField(field)}</dt><dd>{formatAdminValue(field, related[field])}</dd></div>
          ))}
        </dl>
      ) : (
        <p className="admin-related-status"><span className="admin-mono">{id}</span> · Related information is unavailable.</p>
      )}
    </section>
  );
}
