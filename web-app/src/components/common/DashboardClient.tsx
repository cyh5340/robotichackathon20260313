"use client";

import { useEffect, useMemo, useState } from "react";

import { apiRequest } from "@/services/api";
import { transcribeVoiceInstruction } from "@/services/medguard";
import { MedGuardWebSocket } from "@/services/websocket";
import type { NotificationEvent } from "@/services/notifications";

export function DashboardClient() {
  const [health, setHealth] = useState("checking");
  const [events, setEvents] = useState<NotificationEvent[]>([]);
  const [instruction, setInstruction] = useState("");
  const [audioError, setAudioError] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const ws = useMemo(() => new MedGuardWebSocket(), []);
  const recorderState = useMemo(
    () => ({
      recorder: null as MediaRecorder | null,
      stream: null as MediaStream | null,
      chunks: [] as BlobPart[],
    }),
    [],
  );

  const stopTracks = (): void => {
    recorderState.stream
      ?.getTracks()
      .forEach((track: MediaStreamTrack) => track.stop());
    recorderState.stream = null;
  };

  const startRecording = async (): Promise<void> => {
    setAudioError(null);
    if (
      typeof window === "undefined" ||
      !window.MediaRecorder ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      setAudioError("This browser does not support microphone recording.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorderState.stream = stream;
      recorderState.chunks = [];

      const recorder = new MediaRecorder(stream);
      recorderState.recorder = recorder;
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          recorderState.chunks.push(event.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(recorderState.chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        stopTracks();
        setIsRecording(false);

        if (blob.size === 0) {
          setAudioError("No audio captured. Please try again.");
          return;
        }

        setIsTranscribing(true);
        transcribeVoiceInstruction(blob)
          .then((text: string) => setInstruction(text))
          .catch(() =>
            setAudioError(
              "Transcription failed. Check backend and Smallest.ai key.",
            ),
          )
          .finally(() => setIsTranscribing(false));
      };

      recorder.start();
      setIsRecording(true);
    } catch {
      stopTracks();
      setAudioError("Microphone access denied or unavailable.");
    }
  };

  const stopRecording = (): void => {
    if (recorderState.recorder && recorderState.recorder.state !== "inactive") {
      recorderState.recorder.stop();
    }
  };

  useEffect(() => {
    apiRequest<{ status: string }>("/health")
      .then((data) => setHealth(data.status))
      .catch(() => setHealth("unavailable"));

    ws.connect("/ws/events", (payload: unknown) => {
      if (typeof payload !== "object" || payload === null) return;
      const raw = payload as {
        id?: string;
        type?: NotificationEvent["type"];
        title?: string;
        message?: string;
        createdAt?: string;
        created_at?: string;
      };
      if (
        !raw.id ||
        !raw.type ||
        !raw.title ||
        !raw.message ||
        !(raw.createdAt || raw.created_at)
      ) {
        return;
      }
      const maybeEvent: NotificationEvent = {
        id: raw.id,
        type: raw.type,
        title: raw.title,
        message: raw.message,
        createdAt: raw.createdAt ?? raw.created_at ?? "",
      };
      setEvents((current: NotificationEvent[]) =>
        [maybeEvent, ...current].slice(0, 5),
      );
    });

    return () => ws.close();
  }, [ws]);

  return (
    <>
      <section className="card">
        <h2>Backend Health</h2>
        <p>Status: {health}</p>
      </section>
      <section className="card">
        <h2>Recent Notification Events</h2>
        {events.length === 0 ? (
          <p>No realtime events yet.</p>
        ) : (
          <ul>
            {events.map((event: NotificationEvent) => (
              <li key={event.id}>
                <strong>{event.type}</strong>: {event.title}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card">
        <h2>Voice Instruction (Smallest.ai)</h2>
        <p>Record audio and transcribe it into a robot instruction.</p>
        <p>
          <button
            onClick={isRecording ? stopRecording : () => void startRecording()}
            disabled={isTranscribing}
          >
            {isRecording ? "Stop recording" : "Start recording"}
          </button>
        </p>
        {isTranscribing ? <p>Transcribing...</p> : null}
        {instruction ? (
          <p>
            <strong>Instruction:</strong> {instruction}
          </p>
        ) : (
          <p>No instruction captured yet.</p>
        )}
        {audioError ? <p>{audioError}</p> : null}
      </section>
    </>
  );
}
