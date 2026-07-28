#!/usr/bin/env bash
# Compliance posture check for a GenUI deployment. Run from deploy/:
#
#   ./posture.sh [env_file]      (default customer.env)
#
# Answers one question: is this deployment configured the way
# AI-ACT.md and GDPR.md describe? Then prints what actually leaves the
# perimeter with the configuration in front of it.
#
# Deliberately NOT part of smoke.sh. That script asks "is the stack up
# and are tenants isolated", runs after bring-up, and is fail-fast by
# design (`set -e`) because a dead backend makes the next check
# meaningless. This one is read by a different person, needs every
# finding in one pass rather than the first one, and answers about a
# configuration file that can be reviewed before anything is running.
set -uo pipefail

ENV_FILE="${1:-customer.env}"
FAILURES=0

pass() { printf '  PASS  %s\n' "$1"; }
warn() { printf '  WARN  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

# Value of VAR in the env file: last assignment wins, inline comment and
# surrounding whitespace stripped, empty when unset or commented out.
val() {
  local raw
  raw=$(grep -E "^[[:space:]]*$1=" "$ENV_FILE" 2>/dev/null | tail -1) || true
  raw="${raw#*=}"
  raw="${raw%%#*}"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  printf '%s' "$raw"
}

# Same truthiness the backend settings parser accepts.
truthy() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1 | true | yes | on) return 0 ;;
    *) return 1 ;;
  esac
}

# Whether a URL points inside the deployment's own network. Hostname
# heuristic, no DNS and no routing table: it recognises loopback, the
# RFC1918 ranges, the usual internal suffixes and bare docker service
# names. A private host behind a public DNS name reads as external, and
# the check says so rather than guessing. Known ceiling: this is a strong
# hint, not proof. A deployment that needs certainty resolves the name and
# compares it against its actual egress route.
is_local_url() {
  local host="${1#*://}"
  host="${host%%/*}"
  host="${host%%:*}"
  case "$host" in
    localhost | 127.* | ::1 | 10.* | 192.168.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) return 0 ;;
    *.internal | *.local | *.lan | *.svc | *.svc.cluster.local) return 0 ;;
    *.*) return 1 ;;
    "") return 1 ;;
    *) return 0 ;;  # bare name: a compose service or a hosts entry
  esac
}

if [ ! -f "$ENV_FILE" ]; then
  echo "POSTURE FAIL: no env file at '$ENV_FILE'" >&2
  echo "Run from deploy/ after copying customer.env.example, or pass a path." >&2
  exit 1
fi

echo "GenUI deployment posture: $ENV_FILE"
echo
echo "Transparency (deploy/AI-ACT.md)"

if truthy "$(val GENUI_DISCLOSURE_OFF)"; then
  fail "GENUI_DISCLOSURE_OFF is set: served payloads carry no marking of generated content and the library renders no notice. AI-ACT.md describes a deployment where it is on."
else
  pass "AI content disclosure is on (payload marking, DOM markup, visible notice)"
fi

if truthy "$(val DISCLOSURE_EXPOSE_MODEL)"; then
  warn "DISCLOSURE_EXPOSE_MODEL is set: the marking names the model. Allowed, and it publishes an attack target and your vendor choice."
else
  pass "Model name is not published in the marking (default)"
fi

echo
echo "Access control (deploy/TENANT-ISOLATION.md)"

if truthy "$(val GENUI_DEV_OPEN)"; then
  fail "GENUI_DEV_OPEN is set: authentication is disabled and every route is open. It must never appear in a customer deployment."
else
  pass "Dev-open mode is off (fail-closed)"
fi

[ -n "$(val CLIENT_API_KEYS)" ] \
  && pass "CLIENT_API_KEYS declared" \
  || fail "No CLIENT_API_KEYS: without keys there is no tenant identity and no rate-limit subject."

[ -n "$(val ADMIN_API_KEYS)" ] \
  && pass "ADMIN_API_KEYS declared" \
  || fail "No ADMIN_API_KEYS: the control plane, document ingest and the audit read path have no admin identity."

[ -n "$(val USER_TOKEN_SECRETS)" ] \
  && pass "USER_TOKEN_SECRETS declared (per-user routes require a signed identity)" \
  || fail "No USER_TOKEN_SECRETS: the access export and the erasure route have no way to prove the caller is the data subject."

echo
echo "Retention and accountability (deploy/GDPR.md)"

if truthy "$(val AUDIT_LOG_ENABLED)"; then
  pass "Audit trail enabled (what was shown to whom)"
elif [ -z "$(val AUDIT_LOG_ENABLED)" ]; then
  pass "Audit trail enabled (backend default)"
else
  fail "AUDIT_LOG_ENABLED is off: no accountability record, and the access export loses its audit half."
fi

audit_path="$(val AUDIT_LOG_PATH)"
if [ -n "$audit_path" ]; then
  pass "Audit sink: file at $audit_path (queryable from the API; single-worker only, rotation is per-process)"
  workers="$(val WORKERS)"
  [ -n "$workers" ] && [ "$workers" != "1" ] \
    && warn "WORKERS=$workers with a file audit sink: rotation is per-process and the workers will interleave writes to one file."
else
  warn "Audit sink: the 'genui.audit' logger. The lines leave this process for your log pipeline, so the API reports the trail as not queryable and the access export says so. Retention there is your policy, and it holds user identifiers."
fi

ttl="$(val PROFILE_TTL_SECONDS)"
if [ -z "$ttl" ]; then
  warn "PROFILE_TTL_SECONDS unset: the backend default of 90 days applies. Set it explicitly so the retention number is a decision on record."
elif [ "$ttl" = "0" ]; then
  fail "PROFILE_TTL_SECONDS=0: profiles are kept forever. Storage limitation then has to be justified some other way."
else
  pass "Profile retention: ${ttl}s (refreshed on write, so it expires after inactivity)"
fi

echo
echo "What leaves the perimeter with this configuration"

leaves=0
note_out() { printf '  OUT   %s\n' "$1"; leaves=$((leaves + 1)); }
note_in() { printf '  IN    %s\n' "$1"; }

provider="$(val LLM_PROVIDER)"
base_url="$(val OPENAI_BASE_URL)"
case "${provider:-openai}" in
  openai)
    if [ -n "$base_url" ] && is_local_url "$base_url"; then
      note_in "Generation prompts -> $base_url (inside your network)"
    elif [ -n "$base_url" ]; then
      note_out "Generation prompts -> $base_url (OpenAI-compatible endpoint outside your network)"
    else
      note_out "Generation prompts -> OpenAI API"
    fi
    ;;
  anthropic) note_out "Generation prompts -> Anthropic API" ;;
  gemini) note_out "Generation prompts -> Google Gemini API" ;;
  *) note_out "Generation prompts -> LLM_PROVIDER='$provider' (unrecognised here; the backend fails loudly at startup on an unknown provider)" ;;
esac
echo "        Cached zone renders carry the segment archetype, not the visitor's profile."
echo "        Live renders carry the individual profile; /query carries the question text,"
echo "        recent history, the profile and the retrieved chunks. No user id, no API key."

emb_provider="$(val EMBEDDING_PROVIDER)"
emb_url="$(val EMBEDDING_BASE_URL)"
[ -z "$emb_url" ] && emb_url="$base_url"
if [ "$emb_provider" = "gemini" ]; then
  note_out "Document chunks and chat query text -> Google Gemini embeddings"
elif [ -n "$emb_url" ] && is_local_url "$emb_url"; then
  note_in "Document chunks and chat query text -> $emb_url (inside your network)"
elif [ -n "$emb_url" ]; then
  note_out "Document chunks and chat query text -> $emb_url (outside your network)"
else
  note_out "Document chunks and chat query text -> OpenAI embeddings API"
fi

extractor="$(val EXTRACTOR_BACKEND)"
glmocr_key="$(val GLMOCR_API_KEY)"
glmocr_url="$(val GLMOCR_BASE_URL)"
if [ -n "$glmocr_key" ]; then
  note_out "Uploaded documents, whole -> Z.ai cloud OCR (GLMOCR_API_KEY is set)"
elif [ "$extractor" = "glmocr" ] && [ -n "$glmocr_url" ]; then
  if is_local_url "$glmocr_url"; then
    note_in "Uploaded documents -> $glmocr_url (self-hosted OCR, inside your network)"
  else
    note_out "Uploaded documents -> $glmocr_url (OCR endpoint outside your network)"
  fi
else
  note_in "Uploaded documents -> parsed in-process (${extractor:-local})"
fi

if truthy "$(val TRACING_ENABLED)"; then
  otlp="$(val OTLP_ENDPOINT)"
  if [ -z "$otlp" ]; then
    note_in "Traces -> container logs (console exporter)"
  elif is_local_url "$otlp"; then
    note_in "Traces -> $otlp (inside your network)"
  else
    note_out "Traces -> $otlp. Spans carry metadata only, but FastAPI instrumentation records the request path, and the per-user routes carry the user id in the URL."
  fi
else
  note_in "Traces: tracing disabled"
fi

if truthy "$(val AUDIT_LOG_ENABLED)" || [ -z "$(val AUDIT_LOG_ENABLED)" ]; then
  if [ -n "$audit_path" ]; then
    note_in "Audit lines -> $audit_path on this host"
  else
    note_out "Audit lines -> the 'genui.audit' logger, then wherever your log pipeline ships them. They carry user identifiers and what was shown."
  fi
fi

echo
if [ "$leaves" -eq 0 ]; then
  echo "Perimeter: nothing in the processing chain leaves this deployment's network."
else
  echo "Perimeter: $leaves data flow(s) leave this deployment. Each one needs a processor"
  echo "agreement, and a transfer assessment if the recipient is outside the EEA."
  echo "The all-local configuration is written out in deploy/GDPR.md."
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "POSTURE FAIL: $FAILURES check(s) do not match what deploy/AI-ACT.md and deploy/GDPR.md describe." >&2
  exit 1
fi
echo "POSTURE OK"
