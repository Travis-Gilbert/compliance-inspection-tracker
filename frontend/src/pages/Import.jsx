import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { importCSV, importCSVText } from "../utils/api";
import InlineNotice from "../components/InlineNotice";

export default function Import() {
  const [files, setFiles] = useState([]);
  const [importText, setImportText] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const fileRef = useRef();
  const navigate = useNavigate();

  const resetSource = () => {
    setFiles([]);
    setImportText("");
    setImportProgress(null);
    if (fileRef.current) {
      fileRef.current.value = "";
    }
  };

  const setSelectedFiles = (selectedFiles) => {
    const nextFiles = Array.from(selectedFiles || []).filter(Boolean);
    setFiles(nextFiles);
    if (nextFiles.length > 0) {
      setImportText("");
    }
  };

  const handleImport = async () => {
    const trimmedText = importText.trim();
    if (files.length === 0 && !trimmedText) {
      return;
    }

    setImporting(true);
    setImportProgress(null);
    setError("");
    setResult(null);

    try {
      let response;
      if (files.length > 0) {
        response = {
          batch_id: "",
          total_rows: 0,
          imported: 0,
          inserted: 0,
          updated: 0,
          skipped: 0,
          errors: [],
          filesProcessed: files.length,
        };

        for (let index = 0; index < files.length; index += 1) {
          const file = files[index];
          setImportProgress({
            current: index + 1,
            total: files.length,
            name: file.name,
          });

          try {
            const fileResult = await importCSV(file);
            response.batch_id = response.batch_id || fileResult.batch_id;
            response.total_rows += fileResult.total_rows || 0;
            response.imported += fileResult.imported || 0;
            response.inserted += fileResult.inserted || 0;
            response.updated += fileResult.updated || 0;
            response.skipped += fileResult.skipped || 0;
            response.errors.push(
              ...(fileResult.errors || []).map((entry) => `${file.name}: ${entry}`)
            );
          } catch (fileError) {
            response.skipped += 1;
            response.errors.push(`${file.name}: ${fileError.message || "Import failed"}`);
          }
        }
      } else {
        response = await importCSVText(trimmedText);
      }

      setResult(response);
      resetSource();
    } catch (e) {
      setError(e.message || "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);
    setSelectedFiles(event.dataTransfer.files);
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Import Properties</h2>
        <p className="mt-1 text-sm text-gray-500">
          Upload a CSV or paste export text directly. Repeated imports now merge existing properties by parcel ID or normalized address instead of creating duplicate rows.
        </p>
      </div>

      {error && (
        <InlineNotice
          tone="error"
          title="Import failed"
          message={error}
        />
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-3 font-heading font-semibold text-gray-900">Upload CSV File</div>

        <div
          role="button"
          tabIndex={0}
          onClick={() => fileRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              fileRef.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
            dragActive
              ? "border-civic-green bg-civic-green-pale/20"
              : "border-gray-300 hover:border-civic-green hover:bg-civic-green-pale/20"
          } cursor-pointer`}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt"
            multiple
            onChange={(event) => setSelectedFiles(event.target.files)}
            className="hidden"
          />
          {files.length > 0 ? (
            <div>
              <div className="text-sm font-medium text-gray-900">
                {files.length} file{files.length === 1 ? "" : "s"} selected
              </div>
              <div className="mt-2 flex flex-wrap justify-center gap-2 text-xs text-gray-500">
                {files.slice(0, 6).map((file) => (
                  <span key={`${file.name}-${file.lastModified}`} className="rounded bg-gray-100 px-2 py-1">
                    {file.name}
                  </span>
                ))}
                {files.length > 6 && (
                  <span className="rounded bg-gray-100 px-2 py-1">
                    +{files.length - 6} more
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div>
              <div className="text-sm text-gray-600">Click to select one or more CSV files</div>
              <div className="mt-1 text-xs text-gray-400">or drag and drop them here</div>
            </div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-2 font-heading font-semibold text-gray-900">Paste CSV or TSV Text</div>
        <p className="mb-3 text-xs text-gray-500">
          Useful for quick batch ingest from email, spreadsheets, or copied exports.
        </p>
        <textarea
          value={importText}
          onChange={(event) => {
            setImportText(event.target.value);
            if (event.target.value) {
              setFiles([]);
              if (fileRef.current) {
                fileRef.current.value = "";
              }
            }
          }}
          placeholder={`address,parcel_id,buyer_name,program,closing_date,commitment
307 Mason St,41-06-538-004,John Smith,Featured Homes,2024-03-15,$45000`}
          rows={8}
          className="w-full rounded-md border border-gray-200 p-3 text-sm font-mono"
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={handleImport}
          disabled={(files.length === 0 && !importText.trim()) || importing}
          className={`rounded-md px-5 py-2 text-sm font-medium transition-colors ${
            (files.length === 0 && !importText.trim()) || importing
              ? "cursor-not-allowed bg-gray-200 text-gray-500"
              : "bg-civic-green text-white hover:bg-civic-green-light"
          }`}
        >
          {importing
            ? "Importing..."
            : files.length > 0
              ? `Import ${files.length} File${files.length === 1 ? "" : "s"}`
              : "Import Text"}
        </button>

        {(files.length > 0 || importText.trim()) && !importing && (
          <button
            onClick={resetSource}
            className="rounded-md border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Clear
          </button>
        )}

        {importing && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-civic-green border-t-transparent" />
            {importProgress
              ? `Importing ${importProgress.current} of ${importProgress.total}: ${importProgress.name}`
              : `Importing ${files.length > 0 ? "selected files" : "pasted text"}...`}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-2 font-heading font-semibold text-gray-900">Expected Format</div>
        <p className="mb-3 text-xs text-gray-600">
          The tool looks for these columns (names are flexible, order does not matter):
        </p>
        <div className="overflow-auto rounded bg-gray-50 p-3 font-mono text-xs text-gray-700">
          address, parcel_id, buyer_name, email, organization, purchase_type, program, closing_date, commitment, compliance_1st_attempt, compliance_2nd_attempt
          <br />
          307 Mason St, 41-06-538-004, John Smith, john@example.org, Mason Dev LLC, Individual, Featured Homes, 2024-03-15, $45000, 2025-10-01, 2025-11-01
          <br />
          1234 Oak Ave, 41-08-123-005, Jane Doe, jane@example.org, Oak Homes Inc, LLC, Ready for Rehab, 2023-11-20, $80000, ,
        </div>
        <p className="mt-2 text-xs text-gray-500">
          At minimum, each row needs an address. Parcel ID is strongly recommended for safer repeated imports.
        </p>
      </div>

      {result && (
        <InlineNotice
          tone={result.errors?.length ? "warning" : "success"}
          title={result.errors?.length ? "Import complete with issues" : "Import complete"}
          message={[
            result.filesProcessed ? `${result.filesProcessed} files processed` : "",
            result.inserted ? `${result.inserted} new properties added` : "",
            result.updated ? `${result.updated} existing properties merged` : "",
            result.skipped ? `${result.skipped} rows skipped` : "",
          ].filter(Boolean).join("; ") || `${result.imported} properties processed`}
          actionLabel="Go to Dashboard"
          onAction={() => navigate("/")}
        />
      )}

      {result?.errors?.length > 0 && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 p-4">
          <div className="text-sm font-medium text-orange-800">Rows needing attention</div>
          <div className="mt-2 space-y-1 text-xs text-orange-700">
            {result.errors.map((entry, index) => (
              <div key={index}>{entry}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
