<?php
// Kleine doorgeefluik voor de AH mobile api, die zelf geen CORS-headers stuurt.
//
// Let op: alleen hosts uit ALLOWED_HOSTS mogen worden opgevraagd. Zonder die
// controle is dit bestand een open proxy waarmee iedereen willekeurige adressen
// via deze server kan opvragen, inclusief adressen in het interne netwerk.
const ALLOWED_HOSTS = ['api.ah.nl'];
const ALLOWED_METHODS = ['GET', 'POST'];

// ---- CORS ----
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Headers: Content-Type, Authorization");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Content-Type: application/json");

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// ---- Read input ----
$input = json_decode(file_get_contents("php://input"), true);

$url     = $input['url'] ?? null;
$method  = strtoupper($input['method'] ?? 'GET');
$headers = is_array($input['headers'] ?? null) ? $input['headers'] : [];
$body    = $input['body'] ?? null;

if (!$url) {
    http_response_code(400);
    echo json_encode(["error" => "Missing URL"]);
    exit;
}

// ---- Validate target ----
$parts = parse_url($url);
$scheme = strtolower($parts['scheme'] ?? '');
$host   = strtolower($parts['host'] ?? '');

if ($scheme !== 'https' || !in_array($host, ALLOWED_HOSTS, true)) {
    http_response_code(403);
    echo json_encode(["error" => "Target not allowed"]);
    exit;
}

if (!in_array($method, ALLOWED_METHODS, true)) {
    http_response_code(405);
    echo json_encode(["error" => "Method not allowed"]);
    exit;
}

// ---- Build headers ----
$curlHeaders = [];
foreach ($headers as $key => $value) {
    if (!is_string($key) || !is_scalar($value)) {
        continue;
    }
    // Regeleindes weren, anders kan een header extra headers of een tweede
    // request smokkelen.
    if (preg_match('/[\r\n]/', $key . $value)) {
        continue;
    }
    $curlHeaders[] = "$key: $value";
}

// ---- cURL request ----
$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CUSTOMREQUEST  => $method,
    CURLOPT_HTTPHEADER     => $curlHeaders,
    CURLOPT_POSTFIELDS     => is_string($body) ? $body : null,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_CONNECTTIMEOUT => 5,
    CURLOPT_TIMEOUT        => 15,
    CURLOPT_PROTOCOLS      => CURLPROTO_HTTPS,
]);

$response = curl_exec($ch);
$status   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($response === false) {
    http_response_code(502);
    echo json_encode(["error" => "Upstream request failed"]);
    exit;
}

http_response_code($status ?: 502);
echo $response;
