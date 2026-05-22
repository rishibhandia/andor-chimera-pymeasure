# Show every USB device currently present, including unknown / problem devices.
# Run from PowerShell.
Get-PnpDevice -PresentOnly |
    Where-Object { $_.InstanceId -match '^USB\\' -or $_.InstanceId -match '^HID\\' } |
    Sort-Object Class, FriendlyName |
    Select-Object Class, FriendlyName, Status, InstanceId |
    Format-Table -AutoSize -Wrap
