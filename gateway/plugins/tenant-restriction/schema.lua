return {
  name = "tenant-restriction",
  fields = {
    { config = {
        type = "record",
        fields = {
          { required_role = { type = "string", required = false }, }, -- Made optional
        },
      },
    },
  },
}
