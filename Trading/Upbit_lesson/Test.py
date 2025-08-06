with open("C:/Users/ilpus/Desktop/git_folder/Trading/Upbit_MA/nklup.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

print(access_key)
print(secret_key)