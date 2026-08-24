<?php
// ---- CORS ----
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Headers: Content-Type, Authorization");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// ---- Read input ----
$input = json_decode(file_get_contents("php://input"), true);

$url     = $input['url'] ?? null;
$method  = $input['method'] ?? 'GET';
$headers = $input['headers'] ?? [];
$body    = $input['body'] ?? null;

if (!$url) {
    http_response_code(400);
    echo json_encode(["error" => "Missing URL"]);
    exit;
}

// ---- Build headers ----
$curlHeaders = [];
foreach ($headers as $key => $value) {
    $curlHeaders[] = "$key: $value";
}

// ---- cURL request ----
$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CUSTOMREQUEST  => $method,
    CURLOPT_HTTPHEADER     => $curlHeaders,
    CURLOPT_POSTFIELDS     => $body,
]);

$response = curl_exec($ch);
$status   = curl_getinfo($ch, CURLINFO_HTTP_CODE);

http_response_code($status);
echo $response;
