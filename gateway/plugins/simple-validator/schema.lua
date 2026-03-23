return {
  name = "simple-validator",
  fields = {
    { config = {
        type = "record",
        fields = {
          { required_key = { type = "string", default = "secret" }, },
        },
      },
    },
  },
}