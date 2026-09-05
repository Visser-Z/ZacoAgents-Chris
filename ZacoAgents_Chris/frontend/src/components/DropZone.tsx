/**
 * Choosing files, by dropping them or by asking for the picker.
 *
 * There is a real `<input type="file">` underneath, wrapped in the label. Dropping is the
 * addition, not the mechanism: a drop target built out of div handlers alone cannot be reached
 * by a keyboard, and the two people most likely to be loading a round every week are the ones
 * who would notice.
 *
 * Dragging is counted rather than toggled. A dragenter fires again for every child element the
 * pointer crosses, and the matching dragleave fires as it leaves each one, so a plain boolean
 * flickers the whole time the file is held over the box.
 */

import { useRef, useState, type DragEvent } from "react";

export function DropZone({
  id,
  label,
  hint,
  multiple = false,
  files,
  onFiles,
  disabled = false,
}: {
  id: string;
  label: string;
  hint?: string;
  multiple?: boolean;
  files: File[];
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const input = useRef<HTMLInputElement>(null);

  function take(list: FileList | null) {
    if (!list || disabled) return;
    const chosen = Array.from(list);
    onFiles(multiple ? chosen : chosen.slice(0, 1));
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    depth.current = 0;
    setOver(false);
    take(event.dataTransfer.files);
  }

  return (
    <div className="dropzone-wrap">
      <label
        htmlFor={id}
        className={`dropzone${over ? " over" : ""}${disabled ? " disabled" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          depth.current += 1;
          setOver(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => {
          depth.current -= 1;
          if (depth.current <= 0) setOver(false);
        }}
        onDrop={onDrop}
      >
        <strong>{label}</strong>
        <span className="muted">Drop {multiple ? "them" : "it"} here, or choose a file</span>
        {hint ? <span className="dropzone-hint muted">{hint}</span> : null}
        <input
          ref={input}
          id={id}
          type="file"
          multiple={multiple}
          disabled={disabled}
          className="dropzone-input"
          onChange={(event) => take(event.target.files)}
        />
      </label>

      {files.length ? (
        <ul className="chosen">
          {files.map((file) => (
            <li key={`${file.name}-${file.size}`}>
              <span className="mono">{file.name}</span>
              <span className="muted"> — {Math.max(1, Math.round(file.size / 1024))} kB</span>
              <button
                type="button"
                className="link"
                onClick={() => {
                  onFiles(files.filter((other) => other !== file));
                  // The input keeps its own copy of what was chosen, and a file removed here but
                  // still sitting in it comes back the moment anything else is picked.
                  if (input.current) input.current.value = "";
                }}
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
