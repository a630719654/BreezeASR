import { request } from "./http";

export function listTranscripts() {
  return request("/api/transcripts");
}

export function deleteTranscript(transcriptId) {
  return request(`/api/transcripts/${encodeURIComponent(transcriptId)}`, {
    method: "DELETE",
  });
}
