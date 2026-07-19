async function request(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed.");
  return payload;
}

export function createRound(excludeRoundIds) {
  return request("/api/rounds", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ excludeRoundIds }),
  });
}

export function getRound(roundId) {
  return request(`/api/rounds/${encodeURIComponent(roundId)}`);
}

export function submitGuess(roundId, countryIso2) {
  return request(`/api/rounds/${encodeURIComponent(roundId)}/guess`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ countryIso2 }),
  });
}

export function analyzeRound(roundId) {
  return request(`/api/rounds/${encodeURIComponent(roundId)}/analyze`, {
    method: "POST",
  });
}
