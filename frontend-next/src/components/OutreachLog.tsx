"use client";

import { useEffect, useState } from "react";
import { createComm, getComms } from "@/lib/api";

interface Communication {
  id: number;
  property_id: number;
  method: string;
  direction: string;
  date_sent: string | null;
  subject: string;
  body: string;
  response_received: boolean;
  response_date: string | null;
  response_notes: string;
  created_at: string | null;
}

interface OutreachLogProps {
  propertyId: number;
}

const METHOD_OPTIONS = [
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "mail", label: "Mail" },
  { value: "site_visit", label: "Site Visit" },
  { value: "text", label: "Text" },
];

export default function OutreachLog({ propertyId }: OutreachLogProps) {
  const [comms, setComms] = useState<Communication[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [method, setMethod] = useState("email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  const loadComms = async () => {
    setLoading(true);
    try {
      const data = await getComms(propertyId);
      setComms(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadComms();
  }, [propertyId]);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await createComm({
        property_id: propertyId,
        method,
        direction: "outbound",
        subject,
        body,
      });
      setShowForm(false);
      setMethod("email");
      setSubject("");
      setBody("");
      await loadComms();
    } catch {
      // handle silently
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Outreach Log ({comms.length})
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded border border-civic-green px-3 py-1 text-xs font-medium text-civic-green hover:bg-civic-green-pale"
        >
          {showForm ? "Cancel" : "Log Outreach"}
        </button>
      </div>

      {showForm && (
        <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Method</label>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                className="w-full rounded border border-gray-200 px-2 py-1.5 text-xs"
              >
                {METHOD_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Subject</label>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Compliance follow-up"
                className="w-full rounded border border-gray-200 px-2 py-1.5 text-xs"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={3}
              placeholder="Details about this outreach attempt..."
              className="w-full rounded border border-gray-200 px-2 py-1.5 text-xs"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="rounded bg-civic-green px-4 py-1.5 text-xs font-medium text-white hover:bg-civic-green-light disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-xs text-gray-400">Loading communications...</div>
      ) : comms.length === 0 ? (
        <div className="text-xs text-gray-400">No outreach recorded yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100 text-left text-gray-500">
                <th className="pb-2 pr-3 font-medium">Date</th>
                <th className="pb-2 pr-3 font-medium">Method</th>
                <th className="pb-2 pr-3 font-medium">Subject</th>
                <th className="pb-2 font-medium">Response</th>
              </tr>
            </thead>
            <tbody>
              {comms.map((comm) => (
                <tr key={comm.id} className="border-b border-gray-50">
                  <td className="py-2 pr-3 text-gray-700">{comm.date_sent || "N/A"}</td>
                  <td className="py-2 pr-3 capitalize text-gray-700">{comm.method}</td>
                  <td className="py-2 pr-3 text-gray-700">{comm.subject || "No subject"}</td>
                  <td className="py-2">
                    {comm.response_received ? (
                      <span className="text-civic-green font-medium">Yes</span>
                    ) : (
                      <span className="text-gray-400">No</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
