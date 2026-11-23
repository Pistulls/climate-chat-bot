// Viewer-request on the S3 behaviour only: paths without a file extension are app
// routes, so serve index.html. Done here rather than with distribution-wide custom
// error responses, which would also rewrite the API's 403s into index.html.
function handler(event) {
    var request = event.request;
    var last = request.uri.split("/").pop();

    if (last.indexOf(".") === -1) {
        request.uri = "/index.html";
    }

    return request;
}
