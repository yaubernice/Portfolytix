"use client";

import { useEffect, useState } from "react";
import { quoteSocket } from "../lib/api";

function indexQuotes(rows) {
  return Object.fromEntries((rows || []).map((quote) => [quote.ticker, quote]));
}

export function useQuotes() {
  const [quotes, setQuotes] = useState({});
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    let socket;
    let retryTimer;
    let stopped = false;
    let retryDelay = 500;

    function connect() {
      setStatus("connecting");
      try {
        socket = quoteSocket();
      } catch {
        setStatus("unavailable");
        if (!stopped) retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10000);
        return;
      }
      socket.onopen = () => {
        retryDelay = 500;
        setStatus("connected");
      };
      socket.onerror = () => setStatus("unavailable");
      socket.onclose = () => {
        if (stopped) return;
        setStatus("disconnected");
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10000);
      };
      socket.onmessage = (event) => {
        let message;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        if (message.type === "error") {
          setStatus("unavailable");
          socket.close();
        } else if (message.type === "snapshot") {
          setQuotes(indexQuotes(message.quotes));
        } else if (message.type === "quote" && message.quote) {
          setQuotes((current) => ({ ...current, [message.quote.ticker]: message.quote }));
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return { quotes, status };
}
