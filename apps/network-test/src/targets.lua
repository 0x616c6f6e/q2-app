-- Product-independent APP test targets. Edit these URLs, then rebuild the package.
-- No request is sent until the user presses Start / PLAY.
return {
    {name = "HTTPS example", url = "https://example.com/"},
    {name = "HTTP example", url = "http://example.com/"},
    {name = "Local test server", url = "http://127.0.0.1:18080/health"}
}
