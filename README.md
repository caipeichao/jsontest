# jsontest

An API testing tool for human.

## Examples

Write test cases in human json.

``` hjson
{
  uri: http://127.0.0.1/login
  request: {
    username: john
    password: 123456
  }
  response: {
    success: false
    message: "bad password"
  }
}
```

View testing report.

