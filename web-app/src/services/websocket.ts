export type EventHandler = (payload: unknown) => void;

export class MedGuardWebSocket {
  private socket: WebSocket | null = null;

  connect(path: string, onMessage: EventHandler): void {
    const url = `ws://localhost:8000${path}`;
    this.socket = new WebSocket(url);
    this.socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
        onMessage(event.data);
      }
    };
  }

  close(): void {
    this.socket?.close();
    this.socket = null;
  }
}
