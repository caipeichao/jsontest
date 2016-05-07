# jsontest

An API testing tool for human.

## Examples

Write test cases in human json.

``` json
// Test login success
{
  uri: "http://127.0.0.1/login"
  request: {
    username: "john"
    password: "123456"
  }
  response: {
    success: true
    message: "login success"
  }
}
```

View testing report.

