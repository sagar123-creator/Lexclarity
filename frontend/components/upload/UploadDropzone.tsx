"use client";

import { useCallback, useRef, useState } from "react";
import { UploadCloud, FileText, X } from "lucide-react";
import clsx from "clsx";

const ACCEPTED = [".pdf", ".docx", ".txt"];
const MAX_MB = 20;

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadDropzone({
  onFileSelected,
  disabled,
}: {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndSet = useCallback(
    (file: File) => {
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (!ACCEPTED.includes(ext)) {
        setError(`Unsupported file type "${ext}". Please upload a PDF, DOCX, or TXT file.`);
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        setError(`File is too large. Maximum size is ${MAX_MB}MB.`);
        return;
      }
      if (file.size === 0) {
        setError("This file appears to be empty.");
        return;
      }
      setError(null);
      setSelectedFile(file);
      onFileSelected(file);
    },
    [onFileSelected]
  );

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (disabled) return;
          const file = e.dataTransfer.files?.[0];
          if (file) validateAndSet(file);
        }}
        onClick={() => !disabled && inputRef.current?.click()}
        className={clsx(
          "rounded-lg border-2 border-dashed p-12 text-center cursor-pointer transition-colors",
          isDragging ? "border-navy bg-navy/5" : "border-line bg-white hover:bg-paper",
          disabled && "opacity-60 cursor-not-allowed"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) validateAndSet(file);
          }}
        />
        <UploadCloud size={32} className="mx-auto mb-4 text-ink-faint" strokeWidth={1.5} />
        <p className="text-ink font-medium mb-1">
          Drag and drop your document, or click to browse
        </p>
        <p className="text-sm text-ink-faint">
          Supports PDF, DOCX, and TXT — up to {MAX_MB}MB
        </p>
      </div>

      {error && (
        <p className="mt-3 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">
          {error}
        </p>
      )}

      {selectedFile && !error && (
        <div className="mt-4 flex items-center justify-between rounded-md border border-line bg-white px-4 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <FileText size={18} className="text-navy shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink truncate">{selectedFile.name}</p>
              <p className="text-xs text-ink-faint">
                {formatSize(selectedFile.size)} · {selectedFile.type || "document"}
              </p>
            </div>
          </div>
          {!disabled && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFile(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="text-ink-faint hover:text-ink shrink-0"
            >
              <X size={16} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
