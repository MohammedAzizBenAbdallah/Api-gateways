return {
  name = "gateway-signature",
  fields = {
    {
      config = {
        type = "record",
        fields = {
          { secret = { type = "string", required = true }, },
        },
      },
    },
  },
}
