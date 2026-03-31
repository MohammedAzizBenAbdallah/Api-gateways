import { useEffect } from "react";

export function useKeyPress(key, callback) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === key) {
        callback();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [key, callback]);
}
