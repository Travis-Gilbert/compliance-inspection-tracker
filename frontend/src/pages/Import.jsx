import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { importCSV } from "../utils/api";

export default function Import() {
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const fileRef = useRef();
  const navigate = useNavigate();

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const res = await importCSV(file);
      setResult(res);
    } catch (e) {
      setError(e.message);
    }
    setImporting(false);
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Import Properties</h2>
        <p className="text-sm text-gray-500 mt-1">
          Upload a CSV exported from FileMaker or Excel. The tool auto-detects columns for address, parcel ID, buyer name, program, closing date, and committed investment.
        </p>
      </div>

      {/* File upload */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <div className="font-heading font-semibold text-gray-900 mb-3">Upload CSV File</div>

        <div
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-civic-green hover:bg-civic-green-pale/20 transition-colors"
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt"
            onChange={e => setFile(e.target.files[0])}
            className="hidden"
          />
          {file ? (
            <div>
              <div className="text-sm font-medium text-gray-900">{file.name}</div>
              <div className="text-xs text-gray-500 mt-1">{(file.size / 1024).toFixed(1)} KB</div>
            </div>
          ) : (
            <div>
              <div className="text-sm text-gray-500">Click to select a CSV file</div>
              <div className="text-xs text-gray-400 mt-1">or drag and drop</div>
            </div>
          )}
        </div>

        <button
          onClick={handleImport}
          disabled={!file || importing}
          className={`mt-4 px-5 py-2 rounded-md text-sm font-medium transition-colors ${
            !file || importing
              ? "bg-gray-200 text-gray-500 cursor-not-allowed"
              : "bg-civic-green text-white hover:bg-civic-green-light"
          }`}
        >
          {importing ? "Importing..." : "Import"}
        </button>

        {importing && (
          <div className="mt-3 flex items-center gap-2 text-sm text-gray-600">
            <div className="w-4 h-4 border-2 border-civic-green border-t-transparent rounded-full animate-spin" />
            Importing {file?.name}...
          </div>
        )}
      </div>

      {/* Expected format */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <div className="font-heading font-semibold text-gray-900 mb-2">Expected Format</div>
        <p className="text-xs text-gray-600 mb-3">
          The tool looks for these columns (names are flexible, order does not matter):
        </p>
        <div className="bg-gray-50 rounded p-3 font-mono text-xs text-gray-700 overflow-auto">
          address, parcel_id, buyer_name, program, closing_date, commitment<br/>
          307 Mason St, 41-06-538-004, John Smith, Featured Homes, 2024-03-15, $45000<br/>
          1234 Oak Ave, 41-08-123-005, Jane Doe, Ready for Rehab, 2023-11-20, $80000
        </div>
        <p className="text-xs text-gray-500 mt-2">
          At minimum, each row needs an address. All other columns are optional.
        </p>
      </div>

      {/* Results */}
      {result && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm font-medium text-gray-900">Import Complete</div>
          <div className="text-xs text-gray-600 mt-1 space-y-1">
            <div>{result.imported} properties imported</div>
            {result.skipped > 0 && (
              <div className="text-orange-600">{result.skipped} rows skipped (missing address or insert error)</div>
            )}
            {result.total_rows > 0 && (
              <div className="text-gray-500">{result.total_rows} total rows in file</div>
            )}
          </div>
          {result.errors?.length > 0 && (
            <div className="text-xs text-orange-600 mt-2 space-y-0.5">
              {result.errors.map((e, i) => <div key={i}>{e}</div>)}
            </div>
          )}
          <button
            onClick={() => navigate("/")}
            className="mt-3 text-xs font-medium text-civic-green hover:underline"
          >
            Go to Dashboard to run pipeline
          </button>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
